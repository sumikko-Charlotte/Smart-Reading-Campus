"""站内消息：投递、可见性、未读数。

设计要点
--------
1. **两种投递方式**：定向（`user_id`）和按角色广播（`target_roles`）。
   「你的申请通过了」「你参加的活动发了总结」这类属于定向，只有当事人看到；
   全站公告才用广播，避免所有人被别人的审批结果刷屏。
2. **已读一人一条**：`notification_reads` 只存 (notification_id, user_id)，
   广播消息不复制正文，1000 个人看同一条也只有一条消息记录。
3. **可见性统一在 `visible_notifications` 里算**：列表、未读数、标记已读都用同一套规则，
   不会出现「角标显示 3 条、点进去只有 1 条」。
4. 所有函数只 `db.add`，**不 commit**，由调用方在同一个事务里提交，
   保证「业务成功 = 消息发送成功」，不会出现活动已发布但没人收到通知。
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import SignupStatus, UserRole, UserStatus
from app.core.permissions import effective_permissions
from app.core.security import new_id
from app.db.models import ActivitySignup, Notification, NotificationRead, User

# 单次最多扫描的消息条数。演示量级远小于此；上量后改为 SQL 侧按角色过滤或引入
# notification_targets 关联表，届时只需改这一处。
SCAN_LIMIT = 2000


def notify(
    db: Session,
    *,
    type: str,
    title: str,
    content: str = "",
    user_id: str = "",
    target_roles: list[str] | None = None,
    ref_type: str = "",
    ref_id: str = "",
    actor_id: str = "",
    actor_name: str = "",
) -> Notification:
    """写一条消息（不提交事务）。user_id 为空时按 target_roles 广播。"""
    row = Notification(
        notification_id=new_id("notification"),
        type=type,
        title=title,
        content=content,
        ref_type=ref_type,
        ref_id=ref_id,
        user_id=user_id or "",
        target_roles=list(target_roles or []),
        created_by=actor_id,
        created_by_name=actor_name,
    )
    db.add(row)
    return row


def notify_user(db: Session, user_id: str, **kwargs) -> Notification:
    """定向发给一个人。"""
    return notify(db, user_id=user_id, **kwargs)


def notify_users(db: Session, user_ids, **kwargs) -> int:
    """定向发给一批人，自动跳过空值与重复。"""
    seen: set[str] = set()
    count = 0
    for uid in user_ids:
        if not uid or uid in seen:
            continue
        seen.add(uid)
        notify(db, user_id=uid, **kwargs)
        count += 1
    return count


def notify_permission_holders(
    db: Session,
    permission: str,
    *,
    exclude_user_id: str = "",
    **kwargs,
) -> int:
    """发给所有「有效权限」包含该权限点的人。

    直接按角色默认权限判断不够——权限可能被逐项收回或额外授予，
    所以这里逐个算 effective_permissions，与鉴权用的是同一套口径。
    系统管理员天然拥有全部权限，一定会收到。
    """
    rows = db.scalars(
        select(User).where(User.status == UserStatus.ACTIVE.value, User.is_deleted.is_(False))
    ).all()
    receivers = [
        row.user_id
        for row in rows
        if row.user_id != exclude_user_id
        and permission
        in effective_permissions(row.role, row.granted_permissions, row.revoked_permissions)
    ]
    return notify_users(db, receivers, **kwargs)


def activity_signup_user_ids(db: Session, activity_id: str) -> list[str]:
    """活动的有效报名者（待审核或已批准），去重后返回。"""
    rows = db.scalars(
        select(ActivitySignup).where(
            ActivitySignup.activity_id == activity_id,
            ActivitySignup.is_deleted.is_(False),
            ActivitySignup.status.in_((SignupStatus.PENDING.value, SignupStatus.APPROVED.value)),
        )
    ).all()
    return list(dict.fromkeys(row.user_id for row in rows if row.user_id))


def notify_activity_signups(db: Session, activity_id: str, **kwargs) -> int:
    return notify_users(db, activity_signup_user_ids(db, activity_id), **kwargs)


def visible_notifications(db: Session, user: User) -> list[Notification]:
    """当前用户能看到的全部消息（新→旧）。

    规则：定向给我 的 + 广播且我的角色在 target_roles 里 的。
    访客是独立角色，同样按 role 命中广播，不需要账号。
    """
    rows = db.scalars(
        select(Notification)
        .where(Notification.is_deleted.is_(False))
        .order_by(Notification.created_at.desc())
        .limit(SCAN_LIMIT)
    ).all()
    role = user.role or UserRole.STUDENT.value
    return [r for r in rows if r.user_id == user.user_id or (not r.user_id and role in (r.target_roles or []))]


def read_ids(db: Session, user_id: str) -> set[str]:
    rows = db.scalars(
        select(NotificationRead.notification_id).where(NotificationRead.user_id == user_id)
    ).all()
    return set(rows)


def unread_count(db: Session, user: User) -> int:
    if not user:
        return 0
    seen = read_ids(db, user.user_id)
    return sum(1 for row in visible_notifications(db, user) if row.notification_id not in seen)


def mark_read(db: Session, user: User, notification_ids) -> int:
    """标记已读（幂等）。只处理确实对该用户可见的消息，防止越权改他人状态。"""
    visible = {row.notification_id for row in visible_notifications(db, user)}
    seen = read_ids(db, user.user_id)
    count = 0
    for nid in dict.fromkeys(notification_ids):
        if nid not in visible or nid in seen:
            continue
        db.add(
            NotificationRead(
                read_id=new_id("notification_read"),
                notification_id=nid,
                user_id=user.user_id,
            )
        )
        seen.add(nid)
        count += 1
    return count


def mark_all_read(db: Session, user: User) -> int:
    seen = read_ids(db, user.user_id)
    pending = [row.notification_id for row in visible_notifications(db, user) if row.notification_id not in seen]
    return mark_read(db, user, pending)


def mark_related_read(db: Session, user: User, *, ref_type: str, ref_id: str) -> int:
    """把「指向某个业务对象」的消息标为已读。

    审批人点完「通过」后，那条「待审批 XX」的待办就应该消失，
    否则红点会一直挂着已经处理过的事。
    """
    ids = [
        row.notification_id
        for row in visible_notifications(db, user)
        if row.ref_type == ref_type and row.ref_id == ref_id
    ]
    return mark_read(db, user, ids) if ids else 0
