"""站内消息接口：列表、未读数、标记已读。

未读数是顶栏红点的唯一数据源。前端按 10 秒轮询 + 关键操作后主动刷新，
所以「审批通过」这类操作产生的消息，申请人那边最迟 10 秒内红点就会变。
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.response import CODE_NOT_FOUND, BizError, ok, page_result
from app.core.security import CurrentUser, get_current_user
from app.db.base import get_db
from app.db.models import Notification, User
from app.schemas.summary import NotificationOut
from app.services import notification_service as svc

router = APIRouter(tags=["站内消息"])


def _out(row: Notification, read: set[str]) -> dict:
    data = NotificationOut.model_validate(row).model_dump()
    data["is_read"] = row.notification_id in read
    data["scope"] = "user" if row.user_id else "role"
    return data


@router.get("/notifications", summary="我的消息（定向 + 角色广播，带已读状态）")
def list_notifications(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    only_unread: bool = Query(default=False, description="只看未读"),
    type: str = Query(default="", description="按消息类型过滤"),
    current: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user = db.get(User, current.user_id)
    if user is None:
        raise BizError(CODE_NOT_FOUND, "用户不存在")
    rows = svc.visible_notifications(db, user)
    read = svc.read_ids(db, user.user_id)
    if only_unread:
        rows = [row for row in rows if row.notification_id not in read]
    if type:
        rows = [row for row in rows if row.type == type]
    total = len(rows)
    start = (page - 1) * page_size
    items = [_out(row, read) for row in rows[start : start + page_size]]
    data = page_result(items, page, page_size, total)
    # 无论是否过滤，都返回全局未读数，前端红点用它兜底
    data["unread"] = svc.unread_count(db, user)
    return ok(data)


@router.get("/notifications/unread-count", summary="未读消息数（顶栏红点）")
def get_unread_count(current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    user = db.get(User, current.user_id)
    if user is None:
        return ok({"count": 0})
    return ok({"count": svc.unread_count(db, user)})


@router.post("/notifications/{notification_id}/read", summary="标记单条已读")
def read_one(
    notification_id: str,
    current: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user = db.get(User, current.user_id)
    if user is None:
        raise BizError(CODE_NOT_FOUND, "用户不存在")
    changed = svc.mark_read(db, user, [notification_id])
    db.commit()
    return ok({"changed": changed, "unread": svc.unread_count(db, user)})


@router.post("/notifications/read-all", summary="全部标记已读")
def read_all(current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    user = db.get(User, current.user_id)
    if user is None:
        raise BizError(CODE_NOT_FOUND, "用户不存在")
    changed = svc.mark_all_read(db, user)
    db.commit()
    return ok({"changed": changed, "unread": svc.unread_count(db, user)})
