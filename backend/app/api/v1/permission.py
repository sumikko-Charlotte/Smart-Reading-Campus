"""权限目录与权限分配（系统管理员专属）。

安全约束（写在代码里，不只写在文档里）：
1. 不能修改自己的角色/权限 —— 防止自提权、也防止把自己锁死；
2. 不能通过接口创建或提升「系统管理员」—— 防止越权链；
3. `system:permission` 只能由系统管理员天然拥有，不能授予他人；
4. 每次变更都写 permission_logs，谁在什么时候动了谁的权限可追溯。
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.v1.deps import page_query
from app.api.v1.user import user_out
from app.core.enums import NotificationType, PermissionRequestStatus, UserRole
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
from app.db.models import PermissionLog, PermissionRequest, User
from app.schemas.common import PageQuery
from app.schemas.user import (
    PermissionCatalogResponse,
    PermissionGrantRequest,
    PermissionLogOut,
    PermissionRequestCreate,
    PermissionRequestOut,
    PermissionReviewRequest,
    PermissionSummary,
    RoleUpdateRequest,
)
from app.services import notification_service as svc

router = APIRouter(tags=["权限管理"])

SUPER_ONLY = Depends(require_permissions(Permission.SYSTEM_PERMISSION))

PERMISSION_NAMES: dict[str, str] = {item["code"]: item["name"] for item in PERMISSION_CATALOG}


def _names(codes) -> str:
    """把权限码翻成中文，消息里给人看。"""
    return "、".join(PERMISSION_NAMES.get(code, code) for code in codes) or "—"


@router.get("/permissions/catalog", summary="权限目录（分组 + 各角色默认权限）")
def permission_catalog(current: CurrentUser = Depends(get_current_user)):
    """目录本身不含敏感信息：个人中心要用它渲染「我能申请哪些权限」，因此登录即可读。"""
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

    # 让被调整的人立刻知道，而不是某天发现按钮不见了
    granted_codes = [code for code, action, _, _ in changes if action == "grant"]
    revoked_codes = [code for code, action, _, _ in changes if action == "revoke"]
    parts = []
    if granted_codes:
        parts.append(f"新开通：{_names(granted_codes)}")
    if revoked_codes:
        parts.append(f"已收回：{_names(revoked_codes)}")
    if payload.remark:
        parts.append(f"说明：{payload.remark}")
    svc.notify_user(
        db,
        target.user_id,
        type=NotificationType.PERMISSION_CHANGED.value,
        title="你的权限已被管理员调整",
        content="；".join(parts),
        ref_type="user",
        ref_id=target.user_id,
        actor_id=current.user_id,
        actor_name=current.name,
    )
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
    svc.notify_user(
        db,
        target.user_id,
        type=NotificationType.PERMISSION_CHANGED.value,
        title=f"你的角色已由「{ROLE_LABELS.get(before, before)}」调整为「{ROLE_LABELS.get(payload.role, payload.role)}」",
        content="角色变化后权限按新角色默认值重新计算，个人额外授权已清空。",
        ref_type="user",
        ref_id=target.user_id,
        actor_id=current.user_id,
        actor_name=current.name,
    )
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


# ---------------------------------------------------------------- 权限申请
#
# 学生 / 管理员在个人中心提交申请 → 只有系统管理员能看到全部申请并审批。
# 通过时权限即刻写入 target.granted_permissions，同时补一条 PermissionLog，
# 所以「申请单」和「变更流水」两条线可以互相印证。

REQUEST_STATUS_LABELS = {
    PermissionRequestStatus.PENDING.value: "待审批",
    PermissionRequestStatus.APPROVED.value: "已通过",
    PermissionRequestStatus.REJECTED.value: "已驳回",
    PermissionRequestStatus.CANCELLED.value: "已撤回",
}


def _request_out(row: PermissionRequest) -> dict:
    data = PermissionRequestOut.model_validate(row).model_dump()
    data["role_label"] = ROLE_LABELS.get(row.user_role, row.user_role)
    data["status_label"] = REQUEST_STATUS_LABELS.get(row.status, row.status)
    return data


def _request_query(status: str, role: str, keyword: str):
    stmt = select(PermissionRequest)
    if status:
        stmt = stmt.where(PermissionRequest.status == status)
    if role:
        stmt = stmt.where(PermissionRequest.user_role == role)
    if keyword:
        like = f"%{keyword}%"
        stmt = stmt.where(
            PermissionRequest.user_name.like(like)
            | PermissionRequest.student_no.like(like)
            | PermissionRequest.reason.like(like)
        )
    return stmt


@router.post("/permission-requests", status_code=201, summary="提交权限申请（学生 / 管理员）")
def create_permission_request(
    payload: PermissionRequestCreate,
    current: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    codes = sorted({code.strip() for code in payload.permissions if code.strip()})
    if not codes:
        raise BizError(CODE_PARAM_ERROR, "请至少选择一个权限")
    unknown = set(codes) - ALL_PERMISSIONS
    if unknown:
        raise BizError(CODE_PARAM_ERROR, f"未知权限码：{', '.join(sorted(unknown))}")
    if set(codes) & NON_DELEGABLE:
        raise BizError(CODE_FORBIDDEN, "该权限仅系统管理员拥有，不能申请", http_status=403)

    row = db.get(User, current.user_id)
    if row is None:
        raise BizError(CODE_NOT_FOUND, "用户不存在")
    if row.role == UserRole.SUPER_ADMIN.value:
        raise BizError(CODE_PARAM_ERROR, "系统管理员已拥有全部权限，无需申请")

    owned = effective_permissions(row.role, row.granted_permissions, row.revoked_permissions)
    wanted = [code for code in codes if code not in owned]
    if not wanted:
        raise BizError(CODE_ILLEGAL_STATE, "所选权限你当前已经拥有，无需申请")

    pending = db.scalars(
        select(PermissionRequest).where(
            PermissionRequest.user_id == current.user_id,
            PermissionRequest.status == PermissionRequestStatus.PENDING.value,
        )
    ).all()
    duplicated = sorted({code for item in pending for code in (item.permissions or [])} & set(wanted))
    if duplicated:
        raise BizError(CODE_ILLEGAL_STATE, f"以下权限已在审批中：{', '.join(duplicated)}")

    request = PermissionRequest(
        request_id=new_id("permission_request"),
        user_id=row.user_id,
        user_name=row.name,
        student_no=row.student_no,
        user_role=row.role,
        permissions=wanted,
        reason=payload.reason.strip(),
        status=PermissionRequestStatus.PENDING.value,
    )
    db.add(request)
    # 通知所有真正拥有「权限分配」的人（含被额外授予该权限的管理员）
    svc.notify_permission_holders(
        db,
        Permission.SYSTEM_PERMISSION.value,
        exclude_user_id=row.user_id,
        type=NotificationType.PERMISSION_REQUEST.value,
        title=f"{row.name} 申请权限：{_names(wanted)}",
        content=request.reason,
        ref_type="permission_request",
        ref_id=request.request_id,
        actor_id=row.user_id,
        actor_name=row.name,
    )
    db.commit()
    db.refresh(request)
    return ok(_request_out(request))


@router.get("/permission-requests/mine", summary="我的权限申请记录")
def list_my_permission_requests(
    pq: PageQuery = Depends(page_query),
    status: str = Query(default=""),
    current: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if status and status not in REQUEST_STATUS_LABELS:
        raise BizError(CODE_PARAM_ERROR, "status 不合法")
    stmt = select(PermissionRequest).where(PermissionRequest.user_id == current.user_id)
    if status:
        stmt = stmt.where(PermissionRequest.status == status)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(PermissionRequest.created_at.desc())
        .offset((pq.page - 1) * pq.page_size)
        .limit(pq.page_size)
    ).all()
    return ok(page_result([_request_out(r) for r in rows], pq.page, pq.page_size, total))


@router.post("/permission-requests/{request_id}/cancel", summary="撤回自己的待审批申请")
def cancel_permission_request(
    request_id: str,
    current: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = db.get(PermissionRequest, request_id)
    if row is None or row.is_deleted:
        raise BizError(CODE_NOT_FOUND, "申请不存在")
    if row.user_id != current.user_id:
        raise BizError(CODE_FORBIDDEN, "只能撤回自己的申请", http_status=403)
    if row.status != PermissionRequestStatus.PENDING.value:
        raise BizError(CODE_ILLEGAL_STATE, "只有待审批的申请才能撤回")
    row.status = PermissionRequestStatus.CANCELLED.value
    db.commit()
    db.refresh(row)
    return ok(_request_out(row))


@router.get("/permission-requests/summary", summary="申请单统计（系统管理员）", dependencies=[SUPER_ONLY])
def permission_request_summary(db: Session = Depends(get_db)):
    rows = db.execute(
        select(PermissionRequest.status, func.count()).group_by(PermissionRequest.status)
    ).all()
    counts = {status: 0 for status in REQUEST_STATUS_LABELS}
    for status, count in rows:
        counts[status] = count
    return ok({"counts": counts, "pending": counts.get(PermissionRequestStatus.PENDING.value, 0)})


@router.get("/permission-requests", summary="全部权限申请（仅系统管理员）", dependencies=[SUPER_ONLY])
def list_permission_requests(
    pq: PageQuery = Depends(page_query),
    status: str = Query(default="", description="pending / approved / rejected / cancelled"),
    role: str = Query(default="", description="student / admin"),
    db: Session = Depends(get_db),
):
    if status and status not in REQUEST_STATUS_LABELS:
        raise BizError(CODE_PARAM_ERROR, "status 不合法")
    stmt = _request_query(status, role, pq.keyword)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(PermissionRequest.created_at.desc())
        .offset((pq.page - 1) * pq.page_size)
        .limit(pq.page_size)
    ).all()
    return ok(page_result([_request_out(r) for r in rows], pq.page, pq.page_size, total))


@router.post("/permission-requests/{request_id}/review", summary="审批权限申请（仅系统管理员）", dependencies=[SUPER_ONLY])
def review_permission_request(
    request_id: str,
    payload: PermissionReviewRequest,
    current: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = db.get(PermissionRequest, request_id)
    if row is None or row.is_deleted:
        raise BizError(CODE_NOT_FOUND, "申请不存在")
    if row.status != PermissionRequestStatus.PENDING.value:
        raise BizError(CODE_ILLEGAL_STATE, "该申请已处理，不能重复审批")
    if row.user_id == current.user_id:
        raise BizError(CODE_FORBIDDEN, "不能审批自己提交的申请", http_status=403)

    target = db.get(User, row.user_id)
    if target is None or target.is_deleted:
        raise BizError(CODE_NOT_FOUND, "申请人已不存在")
    if target.role == UserRole.SUPER_ADMIN.value:
        raise BizError(CODE_FORBIDDEN, "系统管理员权限不通过申请单调整", http_status=403)

    granted_now: list[str] = []
    if payload.approve:
        granted = set(target.granted_permissions or [])
        revoked = set(target.revoked_permissions or [])
        defaults = ROLE_DEFAULT_PERMISSIONS.get(target.role, set())
        before = effective_permissions(target.role, granted, revoked)
        for code in row.permissions or []:
            if code in before:
                continue
            if code in defaults:
                revoked.discard(code)
            else:
                granted.add(code)
            granted_now.append(code)
        if granted_now:
            target.granted_permissions = sorted(granted)
            target.revoked_permissions = sorted(revoked)
            after = effective_permissions(target.role, granted, revoked)
            for code in granted_now:
                _log(
                    db, current, target, "grant", code,
                    "无权限" if code not in before else "有权限",
                    "有权限" if code in after else "无权限",
                    f"权限申请通过：{row.reason[:80]}",
                )

    row.status = (
        PermissionRequestStatus.APPROVED.value if payload.approve else PermissionRequestStatus.REJECTED.value
    )
    row.reviewer_id = current.user_id
    row.reviewer_name = current.name or "系统管理员"
    row.review_comment = payload.comment.strip()
    row.reviewed_at = datetime.now(timezone.utc)

    # 结果通知申请人：通过的列出实际生效的权限，驳回的附上审批意见
    if payload.approve:
        title = "你的权限申请已通过"
        detail = f"已开通：{_names(granted_now)}" if granted_now else f"申请中的权限已全部拥有：{_names(row.permissions)}"
    else:
        title = "你的权限申请被驳回"
        detail = f"申请权限：{_names(row.permissions)}"
    if row.review_comment:
        detail += f"；审批意见：{row.review_comment}"
    svc.notify_user(
        db,
        target.user_id,
        type=(
            NotificationType.PERMISSION_APPROVED.value
            if payload.approve
            else NotificationType.PERMISSION_REJECTED.value
        ),
        title=title,
        content=detail,
        ref_type="permission_request",
        ref_id=row.request_id,
        actor_id=current.user_id,
        actor_name=row.reviewer_name,
    )
    # 处理完的待办从审批人的红点里移走
    reviewer = db.get(User, current.user_id)
    if reviewer is not None:
        svc.mark_related_read(db, reviewer, ref_type="permission_request", ref_id=row.request_id)
    db.commit()
    db.refresh(row)
    return ok({"request": _request_out(row), "granted": granted_now, "user": user_out(target, current)})
