"""User 相关 Schema。"""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel, RequestModel


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
    role: Literal["student", "librarian", "admin"] = "student"


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
    status: str
    last_login_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class LoginRequest(RequestModel):
    student_no: str = Field(description="学号/工号")
    password: str = Field(default="", description="本轮为占位校验，演示密码 123456")


class LoginResponse(RequestModel):
    token: str
    token_type: str = "Bearer"
    expires_in: int = Field(description="有效期（秒）")
    user: UserOut
