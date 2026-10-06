"""用户与登录：POST /auth/login、GET /users/me、用户 CRUD（RBAC）。"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.v1.deps import page_query
from app.core.config import settings
from app.core.enums import UserRole, UserStatus
from app.core.response import CODE_NOT_FOUND, CODE_UNAUTHORIZED, BizError, ok, page_result
from app.core.security import (
    CurrentUser,
    create_token,
    get_current_user,
    mask_email,
    mask_phone,
    require_roles,
)
from app.db.base import get_db
from app.db.models import User
from app.schemas.common import PageQuery
from app.schemas.user import LoginRequest, LoginResponse, UserCreate, UserOut, UserUpdate

router = APIRouter(tags=["用户与鉴权"])

DEMO_PASSWORD = "123456"


def _to_out(user: User, viewer: CurrentUser | None = None) -> dict:
    data = UserOut.model_validate(user).model_dump()
    is_self = viewer is not None and viewer.user_id == user.user_id
    is_admin = viewer is not None and viewer.role in (UserRole.ADMIN.value, UserRole.LIBRARIAN.value)
    if not (is_self or is_admin):
        data["phone"] = mask_phone(data["phone"])
        data["email"] = mask_email(data["email"])
    return data


@router.post("/auth/login", summary="登录（本轮演示密码 123456）")
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.student_no == payload.student_no, User.is_deleted.is_(False)))
    if user is None or payload.password != DEMO_PASSWORD:
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
            user=UserOut.model_validate(user),
        ).model_dump()
    )


@router.get("/users/me", summary="当前登录用户信息")
def me(user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(User, user.user_id)
    if row is None:
        raise BizError(CODE_NOT_FOUND, "用户不存在")
    return ok(_to_out(row, user))


@router.get("/users", summary="用户列表（管理端）", dependencies=[Depends(require_roles(UserRole.LIBRARIAN, UserRole.ADMIN))])
def list_users(pq: PageQuery = Depends(page_query), role: str = Query(default=""), db: Session = Depends(get_db)):
    stmt = select(User).where(User.is_deleted.is_(False))
    if pq.keyword:
        like = f"%{pq.keyword}%"
        stmt = stmt.where(or_(User.name.like(like), User.student_no.like(like), User.college.like(like)))
    if role:
        stmt = stmt.where(User.role == role)

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    order_col = getattr(User, pq.order_by, User.created_at)
    stmt = stmt.order_by(order_col.desc() if pq.order == "desc" else order_col.asc())
    rows = db.scalars(stmt.offset((pq.page - 1) * pq.page_size).limit(pq.page_size)).all()
    return ok(page_result([UserOut.model_validate(r).model_dump() for r in rows], pq.page, pq.page_size, total))


@router.post("/users", summary="新增用户（管理端）", dependencies=[Depends(require_roles(UserRole.ADMIN))])
def create_user(payload: UserCreate, db: Session = Depends(get_db)):
    exists = db.scalar(select(User).where(User.student_no == payload.student_no))
    if exists:
        raise BizError(1001, "该学号已存在")
    row = User(**payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return ok(UserOut.model_validate(row).model_dump())


@router.patch("/users/{user_id}", summary="更新用户")
def update_user(user_id: str, payload: UserUpdate, current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(User, user_id)
    if row is None or row.is_deleted:
        raise BizError(CODE_NOT_FOUND, "用户不存在")
    if current.user_id != user_id and not current.is_admin:
        raise BizError(1003, "只能修改本人信息", http_status=403)
    for k, v in payload.model_dump(exclude_none=True).items():
        setattr(row, k, v)
    db.commit()
    db.refresh(row)
    return ok(_to_out(row, current))
