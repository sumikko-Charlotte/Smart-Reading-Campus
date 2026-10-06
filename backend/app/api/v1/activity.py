"""活动管理：CRUD + 状态机流转 + AI 推文生成（对应 PC 端活动管理后台）。"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.v1.deps import page_query
from app.core.enums import (
    ACTIVITY_STATUS_LABELS,
    ACTIVITY_STATUS_TRANSITIONS,
    ActivityStatus,
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
from app.core.security import CurrentUser, get_current_user, require_roles
from app.db.base import get_db
from app.db.models import Activity, AIConversation, User
from app.schemas.activity import ActivityCreate, ActivityOut, ActivityStatusChange, ActivityUpdate
from app.schemas.common import PageQuery
from app.services import llm_service

router = APIRouter(prefix="/activities", tags=["活动管理"])


def _to_out(row: Activity) -> dict:
    data = ActivityOut.model_validate(row).model_dump()
    data["status_label"] = ACTIVITY_STATUS_LABELS.get(row.status, row.status)
    return data


def _get_or_404(db: Session, activity_id: str) -> Activity:
    row = db.get(Activity, activity_id)
    if row is None or row.is_deleted:
        raise BizError(CODE_NOT_FOUND, "活动不存在")
    return row


@router.get("", summary="活动列表（分页 + 状态/分类筛选）")
def list_activities(
    pq: PageQuery = Depends(page_query),
    status: str = Query(default="", description="draft/published/signup_closed/ongoing/finished/cancelled"),
    category: str = Query(default=""),
    db: Session = Depends(get_db),
):
    stmt = select(Activity).where(Activity.is_deleted.is_(False))
    if pq.keyword:
        like = f"%{pq.keyword}%"
        stmt = stmt.where(or_(Activity.title.like(like), Activity.summary.like(like), Activity.location.like(like)))
    if status:
        stmt = stmt.where(Activity.status == status)
    if category:
        stmt = stmt.where(Activity.category == category)

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    order_col = getattr(Activity, pq.order_by, Activity.created_at)
    stmt = stmt.order_by(order_col.desc() if pq.order == "desc" else order_col.asc())
    rows = db.scalars(stmt.offset((pq.page - 1) * pq.page_size).limit(pq.page_size)).all()
    return ok(page_result([_to_out(r) for r in rows], pq.page, pq.page_size, total))


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


@router.post("", summary="新建活动（默认草稿）", dependencies=[Depends(require_roles(UserRole.LIBRARIAN, UserRole.ADMIN))])
def create_activity(payload: ActivityCreate, current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    if payload.capacity and payload.capacity < 0:
        raise BizError(CODE_PARAM_ERROR, "名额上限不能为负数")
    organizer = db.get(User, payload.organizer_id or current.user_id)
    row = Activity(
        **payload.model_dump(exclude={"organizer_id"}),
        organizer_id=organizer.user_id if organizer else current.user_id,
        organizer_name=organizer.name if organizer else "",
        status=ActivityStatus.DRAFT.value,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return ok(_to_out(row))


@router.get("/{activity_id}", summary="活动详情")
def get_activity(activity_id: str, db: Session = Depends(get_db)):
    return ok(_to_out(_get_or_404(db, activity_id)))


@router.patch("/{activity_id}", summary="编辑活动", dependencies=[Depends(require_roles(UserRole.LIBRARIAN, UserRole.ADMIN))])
def update_activity(activity_id: str, payload: ActivityUpdate, db: Session = Depends(get_db)):
    row = _get_or_404(db, activity_id)
    if row.status == ActivityStatus.FINISHED.value:
        raise BizError(CODE_ILLEGAL_STATE, "已结束的活动不可编辑")
    for k, v in payload.model_dump(exclude_none=True).items():
        setattr(row, k, v)
    db.commit()
    db.refresh(row)
    return ok(_to_out(row))


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
    row.status = payload.target_status
    if payload.target_status == ActivityStatus.PUBLISHED.value:
        row.published_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    return ok(_to_out(row))


@router.delete("/{activity_id}", summary="删除活动（软删除）", dependencies=[Depends(require_roles(UserRole.ADMIN))])
def delete_activity(activity_id: str, db: Session = Depends(get_db)):
    row = _get_or_404(db, activity_id)
    row.is_deleted = True
    db.commit()
    return ok({"activity_id": activity_id, "deleted": True})


@router.post("/{activity_id}/ai-copy", summary="AI 生成活动宣传推文并回存 ai_copy")
def generate_copy(activity_id: str, style: str = Query(default="xiaohongshu"), db: Session = Depends(get_db)):
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
