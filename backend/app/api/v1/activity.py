"""活动：申办 → 提交审批 → 审批定级 → 发布 → 运营 → 总结。

权限口径（第二阶段）
--------------------
| 动作 | 权限点 | 默认拥有 |
|---|---|---|
| 浏览 | activity:view | 全部角色（含访客） |
| 报名 | activity:signup | 学生、管理员 |
| 申办/管理自己申办的活动 | activity:create | 管理员；学生按需授予 |
| 管理全部活动 | activity:manage_all | 管理员 |
| 审批/定级 | activity:review | 管理员（可被系统管理员收回） |
| 写总结 | activity:summary | 管理员；主办方亦可 |
"""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.v1.deps import page_query
from app.core.enums import (
    ACTIVITY_LEVEL_LABELS,
    ACTIVITY_PUBLIC_STATUSES,
    ACTIVITY_STATUS_LABELS,
    ACTIVITY_STATUS_TRANSITIONS,
    ActivityLevel,
    ActivityStatus,
    NotificationType,
    SignupStatus,
    SummaryStatus,
)
from app.core.permissions import Permission
from app.core.response import (
    CODE_FORBIDDEN,
    CODE_ILLEGAL_STATE,
    CODE_NOT_FOUND,
    CODE_PARAM_ERROR,
    BizError,
    ok,
    page_result,
)
from app.core.security import CurrentUser, get_current_user, get_optional_user, new_id, require_permissions
from app.db.base import get_db
from app.db.models import Activity, ActivitySignup, ActivitySummary, AIConversation, User
from app.schemas.activity import (
    ActivityCreate,
    ActivityOut,
    ActivityReviewRequest,
    ActivitySignupOut,
    ActivitySignupView,
    ActivityStatusChange,
    ActivitySubmitRequest,
    ActivityUpdate,
    EmptyPayload,
)
from app.services import certificate_issue
from app.schemas.common import PageQuery
from app.services import llm_service
from app.services import notification_service as svc

router = APIRouter(prefix="/activities", tags=["活动管理"])


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


PUBLIC_FIELDS = {
    "activity_id", "title", "subtitle", "category", "cover_url", "summary", "content", "location",
    "organizer_name", "signup_start_at", "signup_end_at", "start_at", "end_at", "capacity",
    "signup_count", "status", "level", "need_certificate",
}


def _is_staff_viewer(viewer: CurrentUser | None) -> bool:
    return viewer is not None and viewer.can(Permission.ACTIVITY_MANAGE_ALL.value)


def _to_out(row: Activity, viewer: CurrentUser | None = None) -> dict:
    data = ActivityOut.model_validate(row).model_dump()
    if not _is_staff_viewer(viewer):
        return {key: value for key, value in data.items() if key in PUBLIC_FIELDS}
    return data


def _get_or_404(db: Session, activity_id: str) -> Activity:
    row = db.get(Activity, activity_id)
    if row is None or row.is_deleted:
        raise BizError(CODE_NOT_FOUND, "活动不存在")
    return row


def _my_signup(db: Session, activity_id: str, current: CurrentUser) -> dict | None:
    """当前用户在这场活动里的报名与签到状态。"""
    if not current.user_id:
        return None
    row = db.scalar(
        select(ActivitySignup).where(
            ActivitySignup.activity_id == activity_id,
            ActivitySignup.user_id == current.user_id,
            ActivitySignup.is_deleted.is_(False),
        )
    )
    if row is None:
        return None
    return {
        "signup_id": row.signup_id,
        "status": row.status,
        "signed_up_at": row.signed_up_at,
        "checked_in_at": row.checked_in_at,
        "checked_out_at": row.checked_out_at,
        "certificate_no": row.certificate_no,
    }


def _can_manage(current: CurrentUser, row: Activity) -> bool:
    if current.can(Permission.ACTIVITY_MANAGE_ALL.value):
        return True
    return row.organizer_id == current.user_id and current.can(Permission.ACTIVITY_CREATE.value)


def _require_manage(current: CurrentUser, row: Activity) -> None:
    if not _can_manage(current, row):
        raise BizError(CODE_FORBIDDEN, "只能管理自己申办的活动", http_status=403)


def _validate_publishable(row: Activity) -> None:
    """提交/发布前的数据校验。"""
    signup_deadline = row.signup_end_at or row.start_at
    if row.signup_start_at is not None and _as_utc(row.signup_start_at) >= _as_utc(signup_deadline):
        raise BizError(CODE_PARAM_ERROR, "报名开始时间必须早于报名截止时间")
    if row.end_at is not None and _as_utc(row.end_at) <= _as_utc(row.start_at):
        raise BizError(CODE_PARAM_ERROR, "活动结束时间必须晚于开始时间")
    if row.capacity < 0:
        raise BizError(CODE_PARAM_ERROR, "capacity 必须为非负整数")


@router.get("", summary="活动列表（访客可读；自动按权限过滤可见范围）")
def list_activities(
    pq: PageQuery = Depends(page_query),
    status: str = Query(default="", description="draft/pending_review/rejected/published/signup_closed/ongoing/finished/cancelled"),
    category: str = Query(default=""),
    level: str = Query(default="", description="school / college"),
    current: CurrentUser = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    stmt = select(Activity).where(Activity.is_deleted.is_(False))

    if current.can(Permission.ACTIVITY_MANAGE_ALL.value):
        pass  # 管理员看全部
    elif current.can(Permission.ACTIVITY_CREATE.value):
        # 学生会成员：自己申办的（含草稿/驳回）+ 已公开的
        stmt = stmt.where(
            or_(
                Activity.organizer_id == current.user_id,
                Activity.status.in_([s.value for s in ACTIVITY_PUBLIC_STATUSES]),
            )
        )
    else:
        stmt = stmt.where(Activity.status.in_([s.value for s in ACTIVITY_PUBLIC_STATUSES]))

    if pq.keyword:
        like = f"%{pq.keyword}%"
        stmt = stmt.where(or_(Activity.title.like(like), Activity.summary.like(like), Activity.location.like(like)))
    if status:
        stmt = stmt.where(Activity.status == status)
    if category:
        stmt = stmt.where(Activity.category == category)
    if level:
        stmt = stmt.where(Activity.level == level)

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    if pq.order_by not in {"start_at", "created_at"}:
        raise BizError(CODE_PARAM_ERROR, "order_by 仅允许 start_at 或 created_at")
    order_col = getattr(Activity, pq.order_by)
    stmt = stmt.order_by(order_col.desc() if pq.order == "desc" else order_col.asc())
    rows = db.scalars(stmt.offset((pq.page - 1) * pq.page_size).limit(pq.page_size)).all()
    return ok(page_result([_to_out(r, current) for r in rows], pq.page, pq.page_size, total))


@router.get("/stats", summary="活动总览统计（管理后台首页卡片）")
def activity_stats(db: Session = Depends(get_db)):
    base = select(func.count()).select_from(Activity).where(Activity.is_deleted.is_(False))
    total = db.scalar(base) or 0
    by_status = {s.value: db.scalar(base.where(Activity.status == s.value)) or 0 for s in ActivityStatus}
    signup_sum = db.scalar(
        select(func.coalesce(func.sum(Activity.signup_count), 0)).where(Activity.is_deleted.is_(False))
    ) or 0
    checkin_sum = db.scalar(
        select(func.coalesce(func.sum(Activity.checkin_count), 0)).where(Activity.is_deleted.is_(False))
    ) or 0
    return ok(
        {
            "total": total,
            "by_status": by_status,
            "signup_total": int(signup_sum),
            "checkin_total": int(checkin_sum),
        }
    )


@router.post("", status_code=201, summary="申办活动（默认草稿）", dependencies=[Depends(require_permissions(Permission.ACTIVITY_CREATE))])
def create_activity(payload: ActivityCreate, current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    organizer = db.get(User, current.user_id)
    row = Activity(
        **payload.model_dump(),
        organizer_id=current.user_id,
        organizer_name=organizer.name if organizer else current.name,
        status=ActivityStatus.DRAFT.value,
        level=ActivityLevel.NONE.value,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return ok(_to_out(row, current))


@router.patch("/{activity_id}", summary="编辑活动（主办方或管理员）")
def update_activity(
    activity_id: str,
    payload: ActivityUpdate,
    current: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = _get_or_404(db, activity_id)
    _require_manage(current, row)
    if row.status == ActivityStatus.FINISHED.value:
        raise BizError(CODE_ILLEGAL_STATE, "已结束的活动不可编辑")
    if row.status == ActivityStatus.PENDING_REVIEW.value:
        raise BizError(CODE_ILLEGAL_STATE, "审批中的活动不可编辑，请先撤回或等待审批结果")
    if "capacity" in payload.model_fields_set and payload.capacity is not None and payload.capacity != 0 and payload.capacity < row.signup_count:
        raise BizError(CODE_ILLEGAL_STATE, "名额上限不能低于已报名人数")
    change_labels = {
        "signup_start_at": "报名开始时间",
        "signup_end_at": "报名截止时间",
        "start_at": "活动开始时间",
        "location": "活动地点",
    }
    changed_fields: list[str] = []
    for key, value in payload.model_dump(exclude_unset=True).items():
        if key in {"title", "category", "start_at", "capacity"} and value is None:
            raise BizError(CODE_PARAM_ERROR, f"{key} 不允许为 null")
        if key in change_labels:
            old_value = getattr(row, key)
            if isinstance(old_value, datetime) and isinstance(value, datetime):
                changed = _as_utc(old_value) != _as_utc(value)
            else:
                changed = old_value != value
            if changed:
                changed_fields.append(key)
        setattr(row, key, "" if value is None and key in {"subtitle", "cover_url", "summary", "content", "location", "certificate_template_id"} else value)
    if row.end_at is not None and _as_utc(row.end_at) <= _as_utc(row.start_at):
        raise BizError(CODE_PARAM_ERROR, "end_at 必须晚于 start_at")
    signup_deadline = row.signup_end_at or row.start_at
    if row.signup_start_at is not None and _as_utc(row.signup_start_at) >= _as_utc(signup_deadline):
        raise BizError(CODE_PARAM_ERROR, "signup_start_at 必须早于实际报名截止时间")
    if row.signup_end_at is not None and _as_utc(row.signup_end_at) > _as_utc(row.start_at):
        raise BizError(CODE_PARAM_ERROR, "signup_end_at 不得晚于 start_at")
    if changed_fields:
        details = []
        for key in changed_fields:
            value = getattr(row, key)
            if key == "signup_start_at" and value is None:
                rendered = "发布后开放"
            elif key == "signup_end_at" and value is None:
                rendered = f"活动开始时（{_as_utc(row.start_at).isoformat()}）截止"
            elif isinstance(value, datetime):
                rendered = _as_utc(value).isoformat()
            else:
                rendered = value or "未设置"
            details.append(f"{change_labels[key]}：{rendered}")
        svc.notify_activity_signups(
            db,
            row.activity_id,
            type=NotificationType.ACTIVITY_STATUS.value,
            title=f"你报名的活动信息已更新：{row.title}",
            content="以下信息已调整：" + "；".join(details) + "。请以活动详情页为准。",
            ref_type="activity",
            ref_id=row.activity_id,
            actor_id=current.user_id,
            actor_name=current.name,
        )
    db.commit()
    db.refresh(row)
    return ok(_to_out(row, current))


@router.post("/{activity_id}/submit", summary="提交审批（草稿/被驳回 → 待审批）")
def submit_activity(
    activity_id: str,
    payload: ActivitySubmitRequest | None = None,
    current: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = _get_or_404(db, activity_id)
    _require_manage(current, row)
    if row.status not in (ActivityStatus.DRAFT.value, ActivityStatus.REJECTED.value, ActivityStatus.CANCELLED.value):
        raise BizError(CODE_ILLEGAL_STATE, "只有草稿、被驳回或已取消的活动可以提交审批")
    _validate_publishable(row)
    row.status = ActivityStatus.PENDING_REVIEW.value
    row.submitted_at = datetime.now(timezone.utc)
    row.review_comment = ""
    # 待办式通知：谁有审批权谁收到，且踢掉申请人自己（他有审批权也不能自审）
    svc.notify_permission_holders(
        db,
        Permission.ACTIVITY_REVIEW.value,
        exclude_user_id=current.user_id,
        type=NotificationType.ACTIVITY_REVIEW.value,
        title=f"待审批活动：{row.title}",
        content=f"{current.name or row.organizer_name} 提交了活动申办，请审批并定级（校级/院级）。",
        ref_type="activity",
        ref_id=row.activity_id,
        actor_id=current.user_id,
        actor_name=current.name,
    )
    db.commit()
    db.refresh(row)
    return ok(_to_out(row, current), message="已提交审批")


@router.post(
    "/{activity_id}/review",
    summary="审批活动并定级（校级/院级）",
    dependencies=[Depends(require_permissions(Permission.ACTIVITY_REVIEW))],
)
def review_activity(
    activity_id: str,
    payload: ActivityReviewRequest,
    current: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = _get_or_404(db, activity_id)
    if row.status != ActivityStatus.PENDING_REVIEW.value:
        raise BizError(CODE_ILLEGAL_STATE, "只有待审批的活动可以审批")
    # 审批人不能审批自己申办的活动（系统管理员除外），避免既当运动员又当裁判
    if row.organizer_id == current.user_id and not current.is_super_admin:
        raise BizError(CODE_FORBIDDEN, "不能审批自己申办的活动，请转交其他管理员", http_status=403)

    now = datetime.now(timezone.utc)
    row.reviewed_by = current.user_id
    row.reviewed_by_name = current.name
    row.reviewed_at = now
    row.review_comment = payload.comment
    if payload.approved:
        _validate_publishable(row)
        row.level = payload.level or ActivityLevel.NONE.value
        row.status = ActivityStatus.PUBLISHED.value
        row.published_at = now
        message = f"审批通过，已定为{ACTIVITY_LEVEL_LABELS.get(row.level, row.level)}并发布"
    else:
        row.status = ActivityStatus.REJECTED.value
        message = "已驳回，申办人可修改后重新提交"

    # 审批结果直达申办人
    if row.organizer_id:
        if payload.approved:
            title = f"你申办的活动已通过审批：{row.title}"
            detail = f"定级：{ACTIVITY_LEVEL_LABELS.get(row.level, row.level)}，活动已发布，可开始接受报名。"
        else:
            title = f"你申办的活动被驳回：{row.title}"
            detail = "可按审批意见修改后重新提交。"
        if payload.comment:
            detail += f" 审批意见：{payload.comment}"
        svc.notify_user(
            db,
            row.organizer_id,
            type=(
                NotificationType.ACTIVITY_PUBLISHED.value
                if payload.approved
                else NotificationType.ACTIVITY_REJECTED.value
            ),
            title=title,
            content=detail,
            ref_type="activity",
            ref_id=row.activity_id,
            actor_id=current.user_id,
            actor_name=current.name,
        )
    # 审批完的待办从审批人自己的红点里移除
    reviewer = db.get(User, current.user_id)
    if reviewer is not None:
        svc.mark_related_read(db, reviewer, ref_type="activity", ref_id=row.activity_id)
    db.commit()
    db.refresh(row)
    return ok(_to_out(row, current), message=message)


@router.get("/mine", summary="我参与的活动（报名记录）", dependencies=[Depends(require_permissions(Permission.ACTIVITY_SIGNUP))])
def list_my_activities(
    pq: PageQuery = Depends(page_query),
    current: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    stmt = (
        select(ActivitySignup, Activity)
        .join(Activity, Activity.activity_id == ActivitySignup.activity_id)
        .where(
            ActivitySignup.user_id == current.user_id,
            ActivitySignup.is_deleted.is_(False),
            Activity.is_deleted.is_(False),
        )
    )
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.execute(
        stmt.order_by(ActivitySignup.signed_up_at.desc())
        .offset((pq.page - 1) * pq.page_size)
        .limit(pq.page_size)
    ).all()
    items = [
        {
            **_to_out(activity, current),
            "signup_id": signup.signup_id,
            "signup_status": signup.status,
            "signed_up_at": signup.signed_up_at,
            "checked_in_at": signup.checked_in_at,
            "checked_out_at": signup.checked_out_at,
            "certificate_no": signup.certificate_no,
        }
        for signup, activity in rows
    ]
    result = page_result(items, pq.page, pq.page_size, total)
    result["checkin_count"] = db.scalar(
        select(func.count())
        .select_from(ActivitySignup)
        .join(Activity, Activity.activity_id == ActivitySignup.activity_id)
        .where(
            ActivitySignup.user_id == current.user_id,
            ActivitySignup.is_deleted.is_(False),
            ActivitySignup.checked_in_at.is_not(None),
            Activity.is_deleted.is_(False),
        )
    ) or 0
    return ok(result)


@router.get("/managed", summary="我申办的活动（学生会成员 / 管理员）")
def list_managed_activities(
    pq: PageQuery = Depends(page_query),
    status: str = Query(default=""),
    current: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not current.can(Permission.ACTIVITY_CREATE.value):
        raise BizError(CODE_FORBIDDEN, "当前账号没有申办活动的权限", http_status=403)
    stmt = select(Activity).where(Activity.is_deleted.is_(False))
    if not current.can(Permission.ACTIVITY_MANAGE_ALL.value):
        if current.can(Permission.ACTIVITY_REVIEW.value):
            # 审批人：自己申办的 + 待审批的全部
            stmt = stmt.where(
                or_(
                    Activity.organizer_id == current.user_id,
                    Activity.status == ActivityStatus.PENDING_REVIEW.value,
                )
            )
        else:
            stmt = stmt.where(Activity.organizer_id == current.user_id)
    if status:
        stmt = stmt.where(Activity.status == status)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(Activity.created_at.desc()).offset((pq.page - 1) * pq.page_size).limit(pq.page_size)
    ).all()
    return ok(page_result([_to_out(r, current) for r in rows], pq.page, pq.page_size, total))


@router.get("/feed", summary="活动信息流（活动推送 + 活动总结，按时间与兴趣排序）")
def activity_feed(
    pq: PageQuery = Depends(page_query),
    scope: str = Query(default="all", description="all / joined / mine"),
    current: CurrentUser = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    if scope not in {"all", "joined", "mine"}:
        raise BizError(CODE_PARAM_ERROR, "scope 仅支持 all / joined / mine")

    public_statuses = [status.value for status in ACTIVITY_PUBLIC_STATUSES]
    # 「我发布的」要能看见自己还没过审、被驳回或尚未发布的活动，否则申办完就查不到进度；
    # 其他人的非公开活动仍不出现在信息流里。
    activity_filter = [Activity.is_deleted.is_(False)]
    if scope == "mine" and current.user_id:
        activity_filter.append(
            or_(Activity.status.in_(public_statuses), Activity.organizer_id == current.user_id)
        )
    else:
        activity_filter.append(Activity.status.in_(public_statuses))
    activities = db.scalars(select(Activity).where(*activity_filter)).all()
    activity_map = {row.activity_id: row for row in activities}

    # 总结只放已发布的：草稿还没定稿，点开会是空壳，学生写草稿从活动详情进入
    summaries = db.scalars(
        select(ActivitySummary).where(
            ActivitySummary.is_deleted.is_(False),
            ActivitySummary.status == SummaryStatus.PUBLISHED.value,
        )
    ).all()

    joined_ids: set[str] = set()
    my_signup_status: dict[str, str] = {}
    my_signups: dict[str, dict] = {}
    if current.user_id:
        signups = db.scalars(
            select(ActivitySignup).where(
                ActivitySignup.user_id == current.user_id,
                ActivitySignup.is_deleted.is_(False),
                ActivitySignup.status == SignupStatus.APPROVED.value,
            )
        ).all()
        joined_ids = {row.activity_id for row in signups}
        my_signup_status = {row.activity_id: row.status for row in signups}
        my_signups = {
            row.activity_id: {
                "status": row.status,
                "checked_in_at": row.checked_in_at,
                "checked_out_at": row.checked_out_at,
                "certificate_no": row.certificate_no,
            }
            for row in signups
        }

    # 个性化：参加过同类活动的用户，对同分类的新推送略微加权（12 小时）；
    # 已报名的活动再加重（24 小时），保证「我参加的活动」不会被大量新活动淹没。
    interest_categories = {
        activity_map[activity_id].category
        for activity_id in joined_ids
        if activity_id in activity_map and activity_map[activity_id].category
    }

    def _score(value: datetime | None, category: str = "", activity_id: str = "") -> float:
        if value is None:
            return 0.0
        score = _as_utc(value).timestamp()
        if category and category in interest_categories:
            score += 12 * 3600
        if activity_id and activity_id in joined_ids:
            score += 24 * 3600
        return score

    items: list[dict] = []
    for row in activities:
        if scope == "joined" and row.activity_id not in joined_ids:
            continue
        if scope == "mine" and row.organizer_id != current.user_id:
            continue
        published_at = row.published_at or row.created_at
        items.append(
            {
                "item_type": "activity",
                "item_id": row.activity_id,
                "activity_id": row.activity_id,
                "title": row.title,
                "excerpt": row.subtitle or row.summary or "",
                "cover_url": row.cover_url,
                "category": row.category,
                "status": row.status,
                "level": row.level,
                "location": row.location,
                "start_at": row.start_at,
                "end_at": row.end_at,
                "signup_start_at": row.signup_start_at,
                "signup_end_at": row.signup_end_at,
                "signup_count": row.signup_count,
                "capacity": row.capacity,
                "need_certificate": row.need_certificate,
                "organizer_id": row.organizer_id,
                "organizer_name": row.organizer_name,
                "published_at": published_at,
                "is_joined": row.activity_id in joined_ids,
                "is_mine": row.organizer_id == current.user_id,
                "my_signup_status": my_signup_status.get(row.activity_id, ""),
                "my_signup": my_signups.get(row.activity_id),
                "_score": _score(published_at, row.category, row.activity_id),
            }
        )

    for row in summaries:
        activity = activity_map.get(row.activity_id)
        if activity is None:
            continue
        if scope == "joined" and row.activity_id not in joined_ids:
            continue
        if scope == "mine" and row.author_id != current.user_id:
            continue
        published_at = row.published_at or row.created_at
        items.append(
            {
                "item_type": "summary",
                "item_id": row.summary_id,
                "summary_id": row.summary_id,
                "activity_id": row.activity_id,
                "activity_title": row.activity_title or activity.title,
                "title": row.title,
                "excerpt": row.content[:200],
                "content": row.content,
                "images": row.images or [],
                "author_id": row.author_id,
                "author_name": row.author_name,
                "published_at": published_at,
                "view_count": row.view_count,
                "is_mine": row.author_id == current.user_id,
                "_score": _score(published_at, activity.category, row.activity_id),
            }
        )

    items.sort(key=lambda item: item["_score"], reverse=True)
    total = len(items)
    start = (pq.page - 1) * pq.page_size
    page_items = items[start : start + pq.page_size]
    for item in page_items:
        item.pop("_score", None)
    return ok(page_result(page_items, pq.page, pq.page_size, total))


@router.get("/{activity_id}", summary="活动详情")
def get_activity(activity_id: str, current: CurrentUser = Depends(get_optional_user), db: Session = Depends(get_db)):
    row = _get_or_404(db, activity_id)
    visible = row.status in {s.value for s in ACTIVITY_PUBLIC_STATUSES}
    if not visible and not (_can_manage(current, row) or current.can(Permission.ACTIVITY_REVIEW.value)):
        raise BizError(CODE_NOT_FOUND, "活动不存在")
    data = _to_out(row, current)
    data["my_signup"] = _my_signup(db, activity_id, current)
    return ok(data)


@router.post(
    "/{activity_id}/checkin",
    summary="活动签到（本人）",
    dependencies=[Depends(require_permissions(Permission.ACTIVITY_SIGNUP))],
)
def checkin_activity(
    activity_id: str,
    current: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    activity = db.get(Activity, activity_id)
    if activity is None or activity.is_deleted:
        raise BizError(CODE_NOT_FOUND, "活动不存在")
    if activity.status not in {
        ActivityStatus.PUBLISHED.value,
        ActivityStatus.SIGNUP_CLOSED.value,
        ActivityStatus.ONGOING.value,
        ActivityStatus.FINISHED.value,
    }:
        raise BizError(CODE_ILLEGAL_STATE, "活动尚未开放签到")

    signup = db.scalar(
        select(ActivitySignup).where(
            ActivitySignup.activity_id == activity_id,
            ActivitySignup.user_id == current.user_id,
            ActivitySignup.is_deleted.is_(False),
        )
    )
    if signup is None or signup.status != SignupStatus.APPROVED.value:
        raise BizError(CODE_ILLEGAL_STATE, "请先报名该活动")

    now = datetime.now(timezone.utc)
    start_at = _as_utc(activity.start_at)
    end_at = _as_utc(activity.end_at or activity.start_at)
    if now < start_at - timedelta(minutes=30):
        raise BizError(CODE_ILLEGAL_STATE, "签到尚未开始")
    if now > end_at + timedelta(hours=6):
        raise BizError(CODE_ILLEGAL_STATE, "签到已结束")
    if signup.checked_in_at is not None:
        raise BizError(CODE_ILLEGAL_STATE, "已签到")

    signup.checked_in_at = now
    activity.checkin_count = (activity.checkin_count or 0) + 1
    db.commit()
    db.refresh(signup)
    return ok(
        {"checked_in_at": signup.checked_in_at, "checked_out_at": signup.checked_out_at},
        message="签到成功",
    )


@router.post(
    "/{activity_id}/checkout",
    summary="活动签退（签退后自动发放证书）",
    dependencies=[Depends(require_permissions(Permission.ACTIVITY_SIGNUP))],
)
def checkout_activity(
    activity_id: str,
    current: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    activity = db.get(Activity, activity_id)
    if activity is None or activity.is_deleted:
        raise BizError(CODE_NOT_FOUND, "活动不存在")

    signup = db.scalar(
        select(ActivitySignup).where(
            ActivitySignup.activity_id == activity_id,
            ActivitySignup.user_id == current.user_id,
            ActivitySignup.is_deleted.is_(False),
        )
    )
    if signup is None or signup.status != SignupStatus.APPROVED.value:
        raise BizError(CODE_ILLEGAL_STATE, "未报名该活动")
    if signup.checked_in_at is None:
        raise BizError(CODE_ILLEGAL_STATE, "请先签到")

    now = datetime.now(timezone.utc)
    end_at = _as_utc(activity.end_at or activity.start_at)
    if now > end_at + timedelta(hours=6):
        raise BizError(CODE_ILLEGAL_STATE, "签退已结束")
    if signup.checked_out_at is None:
        signup.checked_out_at = now

    cert = certificate_issue.issue_for_signup(db, activity, signup, issued_by_name="系统自动发放")
    db.commit()
    if cert is not None:
        db.refresh(cert)
    db.refresh(signup)

    certificate = None
    if cert is not None:
        certificate = {
            "certificate_id": cert.certificate_id,
            "serial_no": cert.serial_no,
            "verify_code": cert.verify_code,
            "activity_title": cert.activity_title,
            "issued_at": cert.issued_at,
        }
    return ok(
        {
            "checked_out_at": signup.checked_out_at,
            "certificate_no": signup.certificate_no,
            "certificate": certificate,
        },
        message="签退成功" + ("，证书已发放" if certificate else ""),
    )


@router.post("/{activity_id}/signups", status_code=201, summary="报名（访客不可报名）", dependencies=[Depends(require_permissions(Permission.ACTIVITY_SIGNUP))])
def signup_activity(
    activity_id: str,
    payload: EmptyPayload,
    current: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = db.scalar(select(Activity).where(Activity.activity_id == activity_id).with_for_update())
    if row is None or row.is_deleted:
        raise BizError(CODE_NOT_FOUND, "活动不存在")
    now = datetime.now(timezone.utc)
    deadline = row.signup_end_at or row.start_at
    if (
        row.status != ActivityStatus.PUBLISHED.value
        or (row.signup_start_at is not None and now < _as_utc(row.signup_start_at))
        or now >= _as_utc(deadline)
        or now >= _as_utc(row.start_at)
    ):
        raise BizError(CODE_ILLEGAL_STATE, "报名未开放或已截止")

    existing = db.scalar(
        select(ActivitySignup).where(
            ActivitySignup.activity_id == activity_id,
            ActivitySignup.user_id == current.user_id,
        )
    )
    if existing is not None and existing.status in (SignupStatus.APPROVED.value, SignupStatus.PENDING.value):
        raise BizError(CODE_ILLEGAL_STATE, "已报名")
    if existing is not None and existing.status == SignupStatus.CANCELLED.value:
        existing.status = SignupStatus.APPROVED.value
        existing.signed_up_at = now
        existing.is_deleted = False
        db.flush()
        signup = existing
    else:
        signup = ActivitySignup(
            signup_id=new_id("signup"),
            activity_id=activity_id,
            user_id=current.user_id,
            status=SignupStatus.APPROVED.value,
            signed_up_at=now,
        )
        db.add(signup)
        try:
            db.flush()
        except IntegrityError as exc:
            db.rollback()
            raise BizError(CODE_ILLEGAL_STATE, "已报名") from exc

    reserved = db.execute(
        update(Activity)
        .where(
            Activity.activity_id == activity_id,
            Activity.is_deleted.is_(False),
            (Activity.capacity == 0) | (Activity.signup_count < Activity.capacity),
        )
        .values(signup_count=Activity.signup_count + 1)
    )
    if reserved.rowcount != 1:
        db.rollback()
        raise BizError(CODE_ILLEGAL_STATE, "活动名额已满")
    db.commit()
    db.refresh(signup)
    return ok(ActivitySignupOut.model_validate(signup).model_dump(), message="ok")


@router.get("/{activity_id}/signups", summary="活动报名名单（主办方或管理员）")
def list_activity_signups(activity_id: str, pq: PageQuery = Depends(page_query), current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    row = _get_or_404(db, activity_id)
    if not (_can_manage(current, row) or current.can(Permission.ACTIVITY_REVIEW.value)):
        raise BizError(CODE_FORBIDDEN, "无权查看报名名单", http_status=403)
    stmt = (
        select(ActivitySignup, User.name, User.student_no)
        .join(User, User.user_id == ActivitySignup.user_id)
        .where(ActivitySignup.activity_id == activity_id, ActivitySignup.is_deleted.is_(False))
    )
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.execute(
        stmt.order_by(ActivitySignup.signed_up_at.desc())
        .offset((pq.page - 1) * pq.page_size)
        .limit(pq.page_size)
    ).all()
    items = [
        {**ActivitySignupView.model_validate(signup).model_dump(), "name": name, "student_no": student_no}
        for signup, name, student_no in rows
    ]
    return ok(page_result(items, pq.page, pq.page_size, total))


@router.post("/{activity_id}/status", summary="运营状态流转（报名截止/进行中/结束/取消）")
def change_status(
    activity_id: str,
    payload: ActivityStatusChange,
    current: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = _get_or_404(db, activity_id)
    _require_manage(current, row)
    allowed = ACTIVITY_STATUS_TRANSITIONS.get(row.status, set())
    if payload.target_status not in {s.value for s in allowed}:
        allow_text = "、".join(ACTIVITY_STATUS_LABELS.get(s.value, s.value) for s in allowed) or "无"
        raise BizError(
            CODE_ILLEGAL_STATE,
            f"当前状态「{ACTIVITY_STATUS_LABELS.get(row.status, row.status)}」不能流转到"
            f"「{ACTIVITY_STATUS_LABELS.get(payload.target_status, payload.target_status)}」，可流转：{allow_text}",
        )
    row.status = payload.target_status
    # 报名者关心的是「报名截止 / 开始 / 结束 / 取消」，草稿态流转不必打扰
    if payload.target_status in {
        ActivityStatus.SIGNUP_CLOSED.value,
        ActivityStatus.ONGOING.value,
        ActivityStatus.FINISHED.value,
        ActivityStatus.CANCELLED.value,
    }:
        status_text = ACTIVITY_STATUS_LABELS.get(payload.target_status, payload.target_status)
        cancelled = payload.target_status == ActivityStatus.CANCELLED.value
        svc.notify_activity_signups(
            db,
            row.activity_id,
            type=(
                NotificationType.ACTIVITY_CANCELLED.value
                if cancelled
                else NotificationType.ACTIVITY_STATUS.value
            ),
            title=(
                f"你报名的活动已取消：{row.title}"
                if cancelled
                else f"你报名的活动状态更新：{row.title}"
            ),
            content=(
                "很抱歉，活动因故取消，请留意后续安排。"
                if cancelled
                else f"当前状态：{status_text}。"
            ),
            ref_type="activity",
            ref_id=row.activity_id,
            actor_id=current.user_id,
            actor_name=current.name,
        )
    db.commit()
    db.refresh(row)
    return ok(_to_out(row, current))


@router.delete("/{activity_id}", summary="删除活动（软删除，仅草稿/驳回/取消）")
def delete_activity(activity_id: str, current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    row = _get_or_404(db, activity_id)
    _require_manage(current, row)
    if row.status not in (ActivityStatus.DRAFT.value, ActivityStatus.REJECTED.value, ActivityStatus.CANCELLED.value):
        raise BizError(CODE_ILLEGAL_STATE, "只有草稿、被驳回或已取消的活动可以删除")
    row.is_deleted = True
    db.commit()
    return ok({"activity_id": activity_id, "deleted": True})


@router.post("/{activity_id}/ai-copy", summary="AI 生成活动宣传推文（人工确认后才可发布）")
def generate_copy(
    activity_id: str,
    style: str = Query(default="xiaohongshu"),
    current: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = _get_or_404(db, activity_id)
    _require_manage(current, row)
    text = llm_service.generate_copy(row.title, style)
    row.ai_copy = text
    conv = AIConversation(
        user_id=current.user_id,
        scene="copywriting",
        title=f"活动推文：{row.title}"[:120],
        book_id=None,
        model=llm_service.settings.LLM_MODEL,
        messages=[{"message_id": "msg_local", "role": "assistant", "content": text, "tokens": 0}],
        message_count=1,
        prompt_version=llm_service.settings.PROMPT_VERSION,
    )
    db.add(conv)
    db.commit()
    db.refresh(row)
    return ok({"activity_id": row.activity_id, "ai_copy": text, "conversation_id": conv.conversation_id})
