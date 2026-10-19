"""权限目录与权限分配（系统管理员专属）。

安全约束（写在代码里，不只写在文档里）：
1. 不能修改自己的角色/权限 —— 防止自提权、也防止把自己锁死；
2. 不能通过接口创建或提升「系统管理员」—— 防止越权链；
3. `system:permission` 只能由系统管理员天然拥有，不能授予他人；
4. 每次变更都写 permission_logs，谁在什么时候动了谁的权限可追溯。
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.v1.deps import page_query
from app.api.v1.user import user_out
from app.core.enums import UserRole
from app.core.permissions import (
    ALL_PERMISSIONS,
    NON_DELEGABLE,
    PERMISSION_CATALOG,
    ROLE_DEFAULT_PERMISSIONS,
    ROLE_LABELS,
    effective_permissions,
    permission_groups,
)
from app.core.permissions import Permission
from app.core.response import CODE_FORBIDDEN, CODE_ILLEGAL_STATE, CODE_NOT_FOUND, CODE_PARAM_ERROR, BizError, ok, page_result
from app.core.security import CurrentUser, get_current_user, new_id, require_permissions
from app.db.base import get_db
from app.db.models import PermissionLog, User
from app.schemas.common import PageQuery
from app.schemas.user import (
    PermissionCatalogResponse,
    PermissionGrantRequest,
    PermissionLogOut,
    PermissionSummary,
    RoleUpdateRequest,
)

router = APIRouter(tags=["权限管理"])

SUPER_ONLY = Depends(require_permissions(Permission.SYSTEM_PERMISSION))


@router.get("/permissions/catalog", summary="权限目录（分组 + 各角色默认权限）", dependencies=[SUPER_ONLY])
def permission_catalog():
    return ok(
        PermissionCatalogResponse(
            groups=permission_groups(),
            roles=[{"value": value, "label": label} for value, label in ROLE_LABELS.items()],
            defaults={role: sorted(codes) for role, codes in ROLE_DEFAULT_PERMISSIONS.items()},
        ).model_dump()
    )


def _get_target(db: Session, user_id: str) -> User:
    row = db.get(User, user_id)
    if row is None or row.is_deleted:
        raise BizError(CODE_NOT_FOUND, "用户不存在")
    return row


@router.get("/users/{user_id}/permissions", summary="查看某人的有效权限及来源")
def get_user_permissions(
    user_id: str,
    current: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current.user_id != user_id and not current.can(Permission.SYSTEM_PERMISSION.value):
        raise BizError(CODE_FORBIDDEN, "无权查看他人权限", http_status=403)
    row = _get_target(db, user_id)
    return ok(
        PermissionSummary(
            user_id=row.user_id,
            name=row.name,
            student_no=row.student_no,
            role=row.role,
            role_label=ROLE_LABELS.get(row.role, row.role),
            permissions=sorted(effective_permissions(row.role, row.granted_permissions, row.revoked_permissions)),
            granted_permissions=list(row.granted_permissions or []),
            revoked_permissions=list(row.revoked_permissions or []),
            default_permissions=sorted(ROLE_DEFAULT_PERMISSIONS.get(row.role, set())),
        ).model_dump()
    )


def _log(db: Session, operator: CurrentUser, target: User, action: str, permission: str,
         before: str, after: str, remark: str) -> None:
    db.add(
        PermissionLog(
            log_id=new_id("permission_log"),
            operator_id=operator.user_id,
            operator_name=operator.name,
            target_user_id=target.user_id,
            target_user_name=target.name,
            action=action,
            permission=permission,
            before_value=before,
            after_value=after,
            remark=remark,
        )
    )


@router.patch("/users/{user_id}/permissions", summary="授予 / 收回权限（系统管理员）", dependencies=[SUPER_ONLY])
def update_user_permissions(
    user_id: str,
    payload: PermissionGrantRequest,
    current: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if user_id == current.user_id:
        raise BizError(CODE_FORBIDDEN, "不能修改自己的权限", http_status=403)
    target = _get_target(db, user_id)
    if target.role == UserRole.SUPER_ADMIN.value:
        raise BizError(CODE_FORBIDDEN, "系统管理员权限由角色决定，不可逐项调整", http_status=403)

    grant = {code.strip() for code in payload.grant if code.strip()}
    revoke = {code.strip() for code in payload.revoke if code.strip()}
    unknown = (grant | revoke) - ALL_PERMISSIONS
    if unknown:
        raise BizError(CODE_PARAM_ERROR, f"未知权限码：{', '.join(sorted(unknown))}")
    if grant & revoke:
        raise BizError(CODE_PARAM_ERROR, f"同一权限不能同时授予和收回：{', '.join(sorted(grant & revoke))}")
    if grant & NON_DELEGABLE:
        raise BizError(CODE_FORBIDDEN, "system:permission 仅系统管理员天然拥有，不可授予他人", http_status=403)

    granted = set(target.granted_permissions or [])
    revoked = set(target.revoked_permissions or [])
    defaults = ROLE_DEFAULT_PERMISSIONS.get(target.role, set())
    changes: list[tuple[str, str, str, str]] = []

    for code in sorted(grant):
        before = code in effective_permissions(target.role, granted, revoked)
        if code in defaults:
            revoked.discard(code)  # 本来是默认权限，取消「收回」即可
        else:
            granted.add(code)
        after = code in effective_permissions(target.role, granted, revoked)
        if after and not before:  # 只有真正发生变化才记流水，避免「有→有」噪音
            changes.append((code, "grant", "无权限", "有权限"))

    for code in sorted(revoke):
        before = code in effective_permissions(target.role, granted, revoked)
        if code in defaults:
            revoked.add(code)
        else:
            granted.discard(code)
        after = code in effective_permissions(target.role, granted, revoked)
        if before and not after:
            changes.append((code, "revoke", "有权限", "无权限"))

    if not changes:
        raise BizError(CODE_PARAM_ERROR, "所选权限未发生变化：该用户已处于目标权限状态")

    target.granted_permissions = sorted(granted)
    target.revoked_permissions = sorted(revoked)
    for code, action, before, after in changes:
        _log(db, current, target, action, code, before, after, payload.remark)
    db.commit()
    db.refresh(target)
    return ok(
        {
            "user": user_out(target, current),
            "changed": [{"permission": code, "action": action} for code, action, _, _ in changes],
        }
    )


@router.patch("/users/{user_id}/role", summary="调整角色（系统管理员）", dependencies=[SUPER_ONLY])
def update_user_role(
    user_id: str,
    payload: RoleUpdateRequest,
    current: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if user_id == current.user_id:
        raise BizError(CODE_FORBIDDEN, "不能修改自己的角色", http_status=403)
    target = _get_target(db, user_id)
    if payload.role == UserRole.SUPER_ADMIN.value:
        raise BizError(CODE_FORBIDDEN, "系统管理员不允许通过接口提级，请由运维处理", http_status=403)
    if target.role == UserRole.SUPER_ADMIN.value:
        raise BizError(CODE_FORBIDDEN, "不能降级系统管理员", http_status=403)
    if target.role == payload.role:
        raise BizError(CODE_ILLEGAL_STATE, "角色未发生变化")

    before = target.role
    target.role = payload.role
    # 换角色后清空个人化配置，回到新角色的默认权限，避免遗留脏数据
    target.granted_permissions = []
    target.revoked_permissions = []
    _log(db, current, target, "role_change", "role", ROLE_LABELS.get(before, before),
         ROLE_LABELS.get(payload.role, payload.role), payload.remark)
    db.commit()
    db.refresh(target)
    return ok(user_out(target, current))


@router.get("/permission-logs", summary="权限变更日志", dependencies=[SUPER_ONLY])
def list_permission_logs(
    pq: PageQuery = Depends(page_query),
    target_user_id: str = Query(default=""),
    db: Session = Depends(get_db),
):
    stmt = select(PermissionLog)
    if target_user_id:
        stmt = stmt.where(PermissionLog.target_user_id == target_user_id)
    if pq.keyword:
        like = f"%{pq.keyword}%"
        stmt = stmt.where(
            (PermissionLog.target_user_name.like(like))
            | (PermissionLog.operator_name.like(like))
            | (PermissionLog.permission.like(like))
        )
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(PermissionLog.created_at.desc()).offset((pq.page - 1) * pq.page_size).limit(pq.page_size)
    ).all()
    items = [PermissionLogOut.model_validate(r).model_dump() for r in rows]
    return ok(page_result(items, pq.page, pq.page_size, total))
