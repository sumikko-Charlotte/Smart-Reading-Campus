"""活动管理：CRUD + 状态机流转 + AI 推文生成（对应 PC 端活动管理后台）。"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.v1.deps import page_query
from app.core.enums import (
    ACTIVITY_STATUS_LABELS,
    ACTIVITY_STATUS_TRANSITIONS,
    ActivityStatus,
    SignupStatus,
    UserRole,
)
from app.core.response import (
    CODE_ILLEGAL_STATE,
    CODE_NOT_FOUND,
    CODE_PARAM_ERROR,
    BizError,
    ok,
    page_result,
)
from app.core.security import CurrentUser, get_current_user, new_id, require_roles
from app.db.base import get_db
from app.db.models import Activity, ActivitySignup, AIConversation, User
from app.schemas.activity import (
    ActivityCreate,
    EmptyPayload,
    ActivityOut,
    ActivitySignupOut,
    ActivitySignupView,
    ActivityStatusChange,
    ActivityUpdate,
)
from app.schemas.common import PageQuery
from app.services import llm_service

router = APIRouter(prefix="/activities", tags=["活动管理"])


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


PUBLIC_FIELDS = {
    "activity_id", "title", "subtitle", "category", "cover_url", "summary", "content", "location",
    "organizer_name", "signup_start_at", "signup_end_at", "start_at", "end_at", "capacity",
    "signup_count", "status", "need_certificate",
}


def _to_out(row: Activity, viewer: CurrentUser | None = None) -> dict:
    data = ActivityOut.model_validate(row).model_dump()
    if viewer is None or viewer.role not in (UserRole.LIBRARIAN.value, UserRole.ADMIN.value):
        return {key: value for key, value in data.items() if key in PUBLIC_FIELDS}
    return data


def _get_or_404(db: Session, activity_id: str) -> Activity:
    row = db.get(Activity, activity_id)
    if row is None or row.is_deleted:
        raise BizError(CODE_NOT_FOUND, "活动不存在")
    return row


def _validate_publishable(row: Activity) -> None:
    """发布前校验：对应规范 7.2 第 2 条与 7.5 节的发布约定。"""
    signup_deadline = row.signup_end_at or row.start_at
    if row.signup_start_at is not None and row.signup_start_at >= signup_deadline:
        raise BizError(CODE_PARAM_ERROR, "报名开始时间必须早于报名截止时间")
    if row.end_at is not None and row.end_at <= row.start_at:
        raise BizError(CODE_PARAM_ERROR, "活动结束时间必须晚于开始时间")
    if row.capacity < 0:
        raise BizError(CODE_PARAM_ERROR, "capacity 必须为非负整数")
    if row.need_certificate and not row.certificate_template_id:
        raise BizError(CODE_PARAM_ERROR, "需要证书的活动必须指定 certificate_template_id")


@router.get("", summary="活动列表（分页 + 状态/分类筛选）")
def list_activities(
    pq: PageQuery = Depends(page_query),
    status: str = Query(default="", description="draft/published/signup_closed/ongoing/finished/cancelled"),
    category: str = Query(default=""),
    current: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    stmt = select(Activity).where(Activity.is_deleted.is_(False))
    is_staff = current.role in (UserRole.LIBRARIAN.value, UserRole.ADMIN.value)
    if not is_staff:
        stmt = stmt.where(Activity.status != ActivityStatus.DRAFT.value)
    if pq.keyword:
        like = f"%{pq.keyword}%"
        stmt = stmt.where(or_(Activity.title.like(like), Activity.summary.like(like), Activity.location.like(like)))
    if status:
        stmt = stmt.where(Activity.status == status)
    if category:
        stmt = stmt.where(Activity.category == category)

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
    by_status = {
        s: db.scalar(base.where(Activity.status == s.value)) or 0 for s in ActivityStatus
    }
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


@router.post("", status_code=201, summary="新建活动（默认草稿）", dependencies=[Depends(require_roles(UserRole.LIBRARIAN, UserRole.ADMIN))])
def create_activity(payload: ActivityCreate, current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    organizer = db.get(User, current.user_id)
    row = Activity(
        **payload.model_dump(),
        organizer_id=organizer.user_id if organizer else current.user_id,
        organizer_name=organizer.name if organizer else "",
        status=ActivityStatus.DRAFT.value,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return ok(_to_out(row, current))


@router.get("/{activity_id}", summary="活动详情")
def get_activity(activity_id: str, current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    row = _get_or_404(db, activity_id)
    if row.status == ActivityStatus.DRAFT.value and current.role not in (UserRole.LIBRARIAN.value, UserRole.ADMIN.value):
        raise BizError(CODE_NOT_FOUND, "活动不存在")
    return ok(_to_out(row, current))


@router.patch("/{activity_id}", summary="编辑活动", dependencies=[Depends(require_roles(UserRole.LIBRARIAN, UserRole.ADMIN))])
def update_activity(
    activity_id: str,
    payload: ActivityUpdate,
    current: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = _get_or_404(db, activity_id)
    if row.status == ActivityStatus.FINISHED.value:
        raise BizError(CODE_ILLEGAL_STATE, "已结束的活动不可编辑")
    if "capacity" in payload.model_fields_set and payload.capacity is not None and payload.capacity != 0 and payload.capacity < row.signup_count:
        raise BizError(CODE_ILLEGAL_STATE, "名额上限不能低于已报名人数")
    for key, value in payload.model_dump(exclude_unset=True).items():
        if key in {"title", "category", "start_at", "capacity"} and value is None:
            raise BizError(CODE_PARAM_ERROR, f"{key} 不允许为 null")
        setattr(row, key, "" if value is None and key in {"subtitle", "cover_url", "summary", "content", "location", "certificate_template_id"} else value)
    if row.end_at is not None and _as_utc(row.end_at) <= _as_utc(row.start_at):
        raise BizError(CODE_PARAM_ERROR, "end_at 必须晚于 start_at")
    signup_deadline = row.signup_end_at or row.start_at
    if row.signup_start_at is not None and _as_utc(row.signup_start_at) >= _as_utc(signup_deadline):
        raise BizError(CODE_PARAM_ERROR, "signup_start_at 必须早于实际报名截止时间")
    if row.signup_end_at is not None and _as_utc(row.signup_end_at) > _as_utc(row.start_at):
        raise BizError(CODE_PARAM_ERROR, "signup_end_at 不得晚于 start_at")
    db.commit()
    db.refresh(row)
    return ok(_to_out(row, current))


@router.post("/{activity_id}/publish", summary="发布活动", dependencies=[Depends(require_roles(UserRole.LIBRARIAN, UserRole.ADMIN))])
def publish_activity(
    activity_id: str,
    payload: EmptyPayload | None = None,
    current: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = _get_or_404(db, activity_id)
    if row.status != ActivityStatus.DRAFT.value:
        raise BizError(CODE_ILLEGAL_STATE, "仅草稿活动可以发布")
    _validate_publishable(row)
    row.status = ActivityStatus.PUBLISHED.value
    row.published_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    return ok(_to_out(row, current))


@router.post("/{activity_id}/signups", status_code=201, summary="当前学生报名")
def signup_activity(
    activity_id: str,
    payload: EmptyPayload,
    current: CurrentUser = Depends(require_roles(UserRole.STUDENT)),
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


@router.get("/{activity_id}/signups", summary="活动报名名单", dependencies=[Depends(require_roles(UserRole.LIBRARIAN, UserRole.ADMIN))])
def list_activity_signups(activity_id: str, pq: PageQuery = Depends(page_query), db: Session = Depends(get_db)):
    _get_or_404(db, activity_id)
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


@router.post("/{activity_id}/status", summary="状态流转（状态机校验）", dependencies=[Depends(require_roles(UserRole.LIBRARIAN, UserRole.ADMIN))])
def change_status(activity_id: str, payload: ActivityStatusChange, db: Session = Depends(get_db)):
    row = _get_or_404(db, activity_id)
    allowed = ACTIVITY_STATUS_TRANSITIONS.get(row.status, set())
    if payload.target_status not in {s.value for s in allowed}:
        allow_text = "、".join(ACTIVITY_STATUS_LABELS.get(s.value, s.value) for s in allowed) or "无"
        raise BizError(
            CODE_ILLEGAL_STATE,
            f"当前状态「{ACTIVITY_STATUS_LABELS.get(row.status, row.status)}」不能流转到"
            f"「{ACTIVITY_STATUS_LABELS.get(payload.target_status, payload.target_status)}」，可流转：{allow_text}",
        )
    if payload.target_status == ActivityStatus.PUBLISHED.value:
        _validate_publishable(row)
    row.status = payload.target_status
    if payload.target_status == ActivityStatus.PUBLISHED.value:
        row.published_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    return ok(_to_out(row, CurrentUser(row.organizer_id, UserRole.LIBRARIAN.value)))


@router.delete("/{activity_id}", summary="删除活动（软删除）", dependencies=[Depends(require_roles(UserRole.ADMIN))])
def delete_activity(activity_id: str, db: Session = Depends(get_db)):
    row = _get_or_404(db, activity_id)
    row.is_deleted = True
    db.commit()
    return ok({"activity_id": activity_id, "deleted": True})


@router.post(
    "/{activity_id}/ai-copy",
    summary="AI 生成活动宣传推文并回存 ai_copy",
    dependencies=[Depends(require_roles(UserRole.LIBRARIAN, UserRole.ADMIN))],
)
def generate_copy(
    activity_id: str,
    style: str = Query(default="xiaohongshu"),
    db: Session = Depends(get_db),
):
    row = _get_or_404(db, activity_id)
    text = llm_service.generate_copy(row.title, style)
    row.ai_copy = text
    conv = AIConversation(
        user_id=row.organizer_id,
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
