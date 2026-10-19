"""活动总结与站内推送。

产品口径
--------
活动结束后，主办方（或具备 `activity:summary` 的管理员）写一篇图文总结；
发布时选择推送范围（学生 / 访客 / 管理员），同时写入 notifications，
各端按角色拉取自己的消息流。**总结发布权在人，AI 只做草稿建议**。
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.v1.deps import page_query
from app.core.enums import ActivityStatus, NotificationType, SummaryStatus
from app.core.permissions import ROLE_LABELS, Permission
from app.core.response import CODE_FORBIDDEN, CODE_ILLEGAL_STATE, CODE_NOT_FOUND, CODE_PARAM_ERROR, BizError, ok, page_result
from app.core.security import CurrentUser, get_current_user, new_id, require_permissions
from app.db.base import get_db
from app.db.models import Activity, ActivitySummary, Notification, User
from app.schemas.common import PageQuery
from app.schemas.summary import NotificationOut, SummaryOut, SummaryPublishRequest, SummaryUpsertRequest

router = APIRouter(tags=["活动总结与推送"])

VALID_TARGETS = set(ROLE_LABELS)


def _can_write_summary(current: CurrentUser, activity: Activity | None = None) -> bool:
    if current.can(Permission.ACTIVITY_SUMMARY.value):
        return True
    return (
        activity is not None
        and activity.organizer_id == current.user_id
        and current.can(Permission.ACTIVITY_CREATE.value)
    )


def _summary_out(row: ActivitySummary) -> dict:
    return SummaryOut.model_validate(row).model_dump()


@router.post("/activities/{activity_id}/summary", summary="撰写/更新活动总结（草稿）")
def upsert_summary(
    activity_id: str,
    payload: SummaryUpsertRequest,
    current: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    activity = db.get(Activity, activity_id)
    if activity is None or activity.is_deleted:
        raise BizError(CODE_NOT_FOUND, "活动不存在")
    if not _can_write_summary(current, activity):
        raise BizError(CODE_FORBIDDEN, "只有活动主办方或具备总结权限的管理员可以撰写总结", http_status=403)
    if activity.status not in (ActivityStatus.ONGOING.value, ActivityStatus.FINISHED.value):
        raise BizError(CODE_ILLEGAL_STATE, "活动开始后才能撰写总结")
    if len(payload.images) > 9:
        raise BizError(CODE_PARAM_ERROR, "现场照片最多 9 张")

    row = db.scalar(
        select(ActivitySummary).where(
            ActivitySummary.activity_id == activity_id,
            ActivitySummary.is_deleted.is_(False),
        )
    )
    if row is None:
        row = ActivitySummary(
            summary_id=new_id("summary"),
            activity_id=activity_id,
            activity_title=activity.title,
            author_id=current.user_id,
            author_name=current.name,
            status=SummaryStatus.DRAFT.value,
        )
        db.add(row)
    elif row.status == SummaryStatus.PUBLISHED.value and not current.can(Permission.ACTIVITY_SUMMARY.value):
        raise BizError(CODE_ILLEGAL_STATE, "总结已发布，仅管理员可修改")

    row.title = payload.title
    row.content = payload.content
    row.images = payload.images
    row.author_name = row.author_name or current.name
    db.commit()
    db.refresh(row)
    return ok(_summary_out(row))


@router.get("/activities/{activity_id}/summary", summary="活动总结详情")
def get_summary(
    activity_id: str,
    current: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = db.scalar(
        select(ActivitySummary).where(
            ActivitySummary.activity_id == activity_id,
            ActivitySummary.is_deleted.is_(False),
        )
    )
    if row is None:
        raise BizError(CODE_NOT_FOUND, "该活动还没有总结")
    if row.status != SummaryStatus.PUBLISHED.value and not (
        current.can(Permission.ACTIVITY_SUMMARY.value) or current.user_id == row.author_id
    ):
        raise BizError(CODE_NOT_FOUND, "该活动还没有总结")
    if row.status == SummaryStatus.PUBLISHED.value:
        row.view_count += 1
        db.commit()
        db.refresh(row)
    return ok(_summary_out(row))


@router.post("/summaries/{summary_id}/publish", summary="发布总结并推送到指定角色")
def publish_summary(
    summary_id: str,
    payload: SummaryPublishRequest,
    current: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = db.get(ActivitySummary, summary_id)
    if row is None or row.is_deleted:
        raise BizError(CODE_NOT_FOUND, "总结不存在")
    if not (current.can(Permission.ACTIVITY_SUMMARY.value) or current.user_id == row.author_id):
        raise BizError(CODE_FORBIDDEN, "无权发布该总结", http_status=403)
    if row.status == SummaryStatus.PUBLISHED.value:
        raise BizError(CODE_ILLEGAL_STATE, "总结已发布")

    targets = [role for role in dict.fromkeys(payload.target_roles) if role in VALID_TARGETS]
    if not targets:
        raise BizError(CODE_PARAM_ERROR, f"推送范围非法，可选：{', '.join(sorted(VALID_TARGETS))}")

    row.status = SummaryStatus.PUBLISHED.value
    row.published_at = datetime.now(timezone.utc)
    db.add(
        Notification(
            notification_id=new_id("notification"),
            type=NotificationType.ACTIVITY_SUMMARY.value,
            title=f"活动回顾：{row.title}",
            content=row.content[:200],
            ref_type="activity_summary",
            ref_id=row.summary_id,
            target_roles=targets,
            created_by=current.user_id,
            created_by_name=current.name,
        )
    )
    db.commit()
    db.refresh(row)
    return ok({"summary": _summary_out(row), "pushed_to": targets})


@router.get("/summaries", summary="活动总结列表（全站可见，含访客）")
def list_summaries(
    pq: PageQuery = Depends(page_query),
    activity_id: str = Query(default=""),
    db: Session = Depends(get_db),
):
    stmt = select(ActivitySummary).where(
        ActivitySummary.is_deleted.is_(False),
        ActivitySummary.status == SummaryStatus.PUBLISHED.value,
    )
    if activity_id:
        stmt = stmt.where(ActivitySummary.activity_id == activity_id)
    if pq.keyword:
        like = f"%{pq.keyword}%"
        stmt = stmt.where(or_(ActivitySummary.title.like(like), ActivitySummary.activity_title.like(like)))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(ActivitySummary.published_at.desc())
        .offset((pq.page - 1) * pq.page_size)
        .limit(pq.page_size)
    ).all()
    return ok(page_result([_summary_out(r) for r in rows], pq.page, pq.page_size, total))


@router.get("/notifications", summary="我的推送消息（按当前角色过滤）")
def list_notifications(
    pq: PageQuery = Depends(page_query),
    current: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # target_roles 是 JSON 数组，SQLite 下用 Python 过滤；量级上来后改关联表或 PG 的 JSONB
    rows = db.scalars(
        select(Notification)
        .where(Notification.is_deleted.is_(False))
        .order_by(Notification.created_at.desc())
        .limit(500)
    ).all()
    mine = [r for r in rows if current.role in (r.target_roles or [])]
    total = len(mine)
    start = (pq.page - 1) * pq.page_size
    page_rows = mine[start : start + pq.page_size]
    items = [NotificationOut.model_validate(r).model_dump() for r in page_rows]
    return ok(page_result(items, pq.page, pq.page_size, total))
