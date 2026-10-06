"""User 相关 Schema。"""
from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class UserBase(BaseModel):
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
    role: str = Field(default="student", description="student / librarian / admin")


class UserUpdate(BaseModel):
    name: str | None = None
    college: str | None = None
    major: str | None = None
    class_no: str | None = None
    grade: str | None = None
    phone: str | None = None
    email: str | None = None
    avatar_url: str | None = None
    status: str | None = Field(default=None, description="active / disabled")


class UserOut(ORMModel, UserBase):
    user_id: str
    student_no: str
    role: str
    status: str
    last_login_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class LoginRequest(BaseModel):
    student_no: str = Field(description="学号/工号")
    password: str = Field(default="", description="本轮为占位校验，演示密码 123456")


class LoginResponse(BaseModel):
    token: str
    token_type: str = "Bearer"
    expires_in: int = Field(description="有效期（秒）")
    user: UserOut
