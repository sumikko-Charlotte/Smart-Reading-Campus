"""User 相关 Schema（第二阶段：三角色 + 双级管理员 + 逐项权限）。"""
from datetime import datetime
from typing import Literal

from pydantic import Field

from app.schemas.common import ORMModel, RequestModel

RoleLiteral = Literal["visitor", "student", "admin", "super_admin"]


class UserBase(RequestModel):
    name: str = Field(min_length=1, max_length=64)
    college: str = ""
    major: str = ""
    class_no: str = ""
    grade: str = ""
    phone: str = ""
    email: str = ""
    avatar_url: str = ""


class UserCreate(UserBase):
    student_no: str = Field(min_length=3, max_length=32, description="学号/工号，登录账号")
    role: RoleLiteral = "student"


class UserUpdate(RequestModel):
    name: str | None = None
    college: str | None = None
    major: str | None = None
    class_no: str | None = None
    grade: str | None = None
    phone: str | None = None
    email: str | None = None
    avatar_url: str | None = None
    status: Literal["active", "disabled"] | None = None


class UserOut(ORMModel, UserBase):
    user_id: str
    student_no: str
    role: str
    role_label: str = ""
    status: str
    # 有效权限（角色默认 - 收回 + 额外授予），由接口计算后填入
    permissions: list[str] = Field(default_factory=list)
    granted_permissions: list[str] = Field(default_factory=list)
    revoked_permissions: list[str] = Field(default_factory=list)
    last_login_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class LoginRequest(RequestModel):
    student_no: str = Field(description="学号/工号")
    password: str = Field(default="", description="注册用户为自己的密码；演示账号为 123456")


class RegisterRequest(RequestModel):
    """注册：只开放「学生 / 普通管理员」两种身份，访客免注册、系统管理员不可注册。"""

    student_no: str = Field(min_length=3, max_length=32, description="学号/工号，注册后作为登录账号")
    name: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=6, max_length=64)
    role: Literal["student", "admin"] = Field(default="student", description="student=学生，admin=普通管理员")
    college: str = Field(default="", max_length=64)
    major: str = Field(default="", max_length=64)
    grade: str = Field(default="", max_length=16)
    class_no: str = Field(default="", max_length=32)
    phone: str = Field(default="", max_length=32)
    email: str = Field(default="", max_length=128)


class PasswordChangeRequest(RequestModel):
    old_password: str = Field(default="", max_length=64)
    new_password: str = Field(min_length=6, max_length=64)


class LoginResponse(RequestModel):
    token: str
    token_type: str = "Bearer"
    expires_in: int = Field(description="有效期（秒）")
    user: UserOut


class PermissionGrantRequest(RequestModel):
    """权限分配：一次提交「授予」与「收回」两组权限码。"""

    grant: list[str] = Field(default_factory=list, description="额外授予的权限码")
    revoke: list[str] = Field(default_factory=list, description="从角色默认权限中收回的权限码")
    remark: str = Field(default="", max_length=255, description="变更原因，写入审计日志")


class PermissionSummary(RequestModel):
    """某个用户的有效权限及其来源，供管理端展示。"""

    user_id: str
    name: str
    student_no: str
    role: str
    role_label: str
    permissions: list[str]
    granted_permissions: list[str]
    revoked_permissions: list[str]
    default_permissions: list[str]


class RoleUpdateRequest(RequestModel):
    role: RoleLiteral
    remark: str = Field(default="", max_length=255)


class PermissionCatalogItem(RequestModel):
    code: str
    name: str
    group: str
    description: str
    risk: str


class PermissionCatalogGroup(RequestModel):
    group: str
    items: list[PermissionCatalogItem]


class PermissionCatalogResponse(RequestModel):
    groups: list[PermissionCatalogGroup]
    roles: list[dict]
    defaults: dict


class PermissionLogOut(ORMModel):
    log_id: str
    operator_id: str
    operator_name: str
    target_user_id: str
    target_user_name: str
    action: str
    permission: str
    before_value: str
    after_value: str
    remark: str
    created_at: datetime


# ------------------------------------------------------------ 权限申请


class PermissionRequestCreate(RequestModel):
    permissions: list[str] = Field(min_length=1, description="本次申请的一到多个权限码")
    reason: str = Field(min_length=5, max_length=500, description="申请理由，管理员审批依据")


class PermissionReviewRequest(RequestModel):
    approve: bool
    comment: str = Field(default="", max_length=255, description="审批意见，驳回时建议填写")


class PermissionRequestOut(ORMModel):
    request_id: str
    user_id: str
    user_name: str
    student_no: str
    user_role: str
    role_label: str = ""
    permissions: list[str] = Field(default_factory=list)
    reason: str
    status: str
    status_label: str = ""
    reviewer_name: str = ""
    review_comment: str = ""
    reviewed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
