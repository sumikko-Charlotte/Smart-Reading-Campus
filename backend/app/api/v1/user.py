"""用户与登录：登录、当前用户、用户 CRUD。

角色只有 4 个取值（visitor/student/admin/super_admin），但**权限逐项可配**，
具体校验在 app.core.permissions 与 app.api.v1.permission。
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.v1.deps import page_query
from app.core.config import settings
from app.core.enums import UserRole, UserStatus
from app.core.permissions import ROLE_LABELS, effective_permissions
from app.core.response import CODE_NOT_FOUND, CODE_PARAM_ERROR, CODE_UNAUTHORIZED, BizError, ok, page_result
from app.core.security import (
    CurrentUser,
    check_login_password,
    create_token,
    get_current_user,
    hash_password,
    mask_email,
    mask_phone,
    new_id,
    require_permissions,
)
from app.db.base import get_db
from app.db.models import User
from app.core.permissions import Permission
from app.schemas.common import PageQuery
from app.schemas.user import (
    LoginRequest,
    LoginResponse,
    PasswordChangeRequest,
    RegisterRequest,
    UserCreate,
    UserOut,
    UserUpdate,
)

router = APIRouter(tags=["用户与鉴权"])


def user_out(user: User, viewer: CurrentUser | None = None) -> dict:
    """统一出口：带有效权限 + 按查看者脱敏联系方式。"""
    data = UserOut.model_validate(user).model_dump()
    data["permissions"] = sorted(
        effective_permissions(user.role, user.granted_permissions, user.revoked_permissions)
    )
    data["role_label"] = ROLE_LABELS.get(user.role, user.role)
    is_self = viewer is not None and viewer.user_id == user.user_id
    can_see_all = viewer is not None and viewer.can(Permission.SYSTEM_USER.value)
    if not (is_self or can_see_all):
        data["phone"] = mask_phone(data["phone"])
        data["email"] = mask_email(data["email"])
    return data


@router.post("/auth/login", summary="登录（注册用户用自己密码，演示账号统一 123456）")
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.student_no == payload.student_no, User.is_deleted.is_(False)))
    if user is None or not check_login_password(payload.password, user.password_hash):
        raise BizError(CODE_UNAUTHORIZED, "学号或密码错误")
    if user.status != UserStatus.ACTIVE.value:
        raise BizError(CODE_UNAUTHORIZED, "账号已被禁用，请联系管理员")

    user.last_login_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(user)

    token = create_token(user.user_id, user.role)
    return ok(
        LoginResponse(
            token=token,
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            user=UserOut.model_validate(user_out(user, CurrentUser(user.user_id, user.role))),
        ).model_dump()
    )


@router.post("/auth/register", status_code=201, summary="注册（学生或普通管理员），注册成功即登录")
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    # 访客免注册；系统管理员只能由运维在库里设置，接口不开放
    if payload.role not in (UserRole.STUDENT.value, UserRole.ADMIN.value):
        raise BizError(CODE_PARAM_ERROR, "只能注册为学生或普通管理员")

    exists = db.scalar(select(User).where(User.student_no == payload.student_no))
    if exists:
        raise BizError(CODE_PARAM_ERROR, "该学号/工号已注册，请直接登录")

    row = User(
        user_id=new_id("user"),
        student_no=payload.student_no,
        name=payload.name,
        role=payload.role,
        college=payload.college,
        major=payload.major,
        grade=payload.grade,
        class_no=payload.class_no,
        phone=payload.phone,
        email=payload.email,
        password_hash=hash_password(payload.password),
        granted_permissions=[],
        revoked_permissions=[],
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    token = create_token(row.user_id, row.role)
    return ok(
        LoginResponse(
            token=token,
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            user=UserOut.model_validate(user_out(row, CurrentUser(row.user_id, row.role))),
        ).model_dump()
    )


@router.post("/auth/guest", summary="访客进入（无需账号，返回只读身份）")
def guest_login(db: Session = Depends(get_db)):
    """一次性访客入口：复用 guest 账号，便于前端「一键以访客身份浏览」。"""
    row = db.scalar(select(User).where(User.student_no == "guest", User.is_deleted.is_(False)))
    if row is None:
        row = User(
            user_id=new_id("user"),
            student_no="guest",
            name="访客",
            role=UserRole.VISITOR.value,
            password_hash="",
            granted_permissions=[],
            revoked_permissions=[],
        )
        db.add(row)
    row.last_login_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    token = create_token(row.user_id, row.role)
    return ok(
        LoginResponse(
            token=token,
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            user=UserOut.model_validate(user_out(row, CurrentUser(row.user_id, row.role))),
        ).model_dump()
    )


@router.get("/users/me", summary="当前登录用户信息（含有效权限）")
def me(user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(User, user.user_id)
    if row is None:
        raise BizError(CODE_NOT_FOUND, "用户不存在")
    return ok(user_out(row, user))


@router.patch("/users/me/password", summary="修改本人密码")
def change_password(
    payload: PasswordChangeRequest,
    current: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = db.get(User, current.user_id)
    if row is None:
        raise BizError(CODE_NOT_FOUND, "用户不存在")
    if row.role == UserRole.VISITOR.value:
        raise BizError(1003, "访客为公共只读账号，不支持设置密码", http_status=403)
    if not check_login_password(payload.old_password, row.password_hash):
        raise BizError(CODE_PARAM_ERROR, "原密码不正确")
    if payload.old_password == payload.new_password:
        raise BizError(CODE_PARAM_ERROR, "新密码不能与原密码相同")
    row.password_hash = hash_password(payload.new_password)
    db.commit()
    return ok({"updated": True})


@router.get(
    "/users",
    summary="用户列表（管理端）",
    dependencies=[Depends(require_permissions(Permission.SYSTEM_USER))],
)
def list_users(
    pq: PageQuery = Depends(page_query),
    role: str = Query(default="", description="visitor/student/admin/super_admin"),
    current: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    stmt = select(User).where(User.is_deleted.is_(False))
    if pq.keyword:
        like = f"%{pq.keyword}%"
        stmt = stmt.where(or_(User.name.like(like), User.student_no.like(like), User.college.like(like)))
    if role:
        stmt = stmt.where(User.role == role)

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    if pq.order_by not in {"created_at", "student_no", "name"}:
        raise BizError(1001, "order_by 不合法")
    order_col = getattr(User, pq.order_by)
    stmt = stmt.order_by(order_col.desc() if pq.order == "desc" else order_col.asc())
    rows = db.scalars(stmt.offset((pq.page - 1) * pq.page_size).limit(pq.page_size)).all()
    return ok(page_result([user_out(r, current) for r in rows], pq.page, pq.page_size, total))


@router.post(
    "/users",
    status_code=201,
    summary="新增用户（管理端）",
    dependencies=[Depends(require_permissions(Permission.SYSTEM_USER))],
)
def create_user(payload: UserCreate, db: Session = Depends(get_db)):
    if payload.role == UserRole.SUPER_ADMIN.value:
        raise BizError(1003, "系统管理员不允许通过接口创建，请由运维在数据库中设置", http_status=403)
    exists = db.scalar(select(User).where(User.student_no == payload.student_no))
    if exists:
        raise BizError(1001, "该学号已存在")
    row = User(**payload.model_dump(), granted_permissions=[], revoked_permissions=[])
    db.add(row)
    db.commit()
    db.refresh(row)
    return ok(user_out(row, CurrentUser(row.user_id, row.role)))


@router.patch("/users/{user_id}", summary="更新用户（本人或具有用户管理权限者）")
def update_user(user_id: str, payload: UserUpdate, current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    # 前端用 PATCH /users/me 保存本人资料，这里把 me 折叠成当前用户
    if user_id == "me":
        user_id = current.user_id
    row = db.get(User, user_id)
    if row is None or row.is_deleted:
        raise BizError(CODE_NOT_FOUND, "用户不存在")
    if current.user_id != user_id and not current.can(Permission.SYSTEM_USER.value):
        raise BizError(1003, "只能修改本人信息", http_status=403)
    # 访客是所有人共用的一行数据，改资料会互相覆盖，直接拒绝
    if current.user_id == user_id and row.role == UserRole.VISITOR.value:
        raise BizError(1003, "访客为公共只读账号，资料不可修改", http_status=403)
    for key, value in payload.model_dump(exclude_unset=True).items():
        if value is None and key in {"name", "status"}:
            raise BizError(1001, f"{key} 不允许为 null")
        if value is None and key in {"college", "major", "class_no", "grade", "phone", "email", "avatar_url"}:
            value = ""
        # 自己不能把自己禁用，避免唯一管理员被锁在门外
        if key == "status" and current.user_id == user_id and value != UserStatus.ACTIVE.value:
            raise BizError(1005, "不能禁用当前登录账号")
        setattr(row, key, value)
    db.commit()
    db.refresh(row)
    return ok(user_out(row, current))
