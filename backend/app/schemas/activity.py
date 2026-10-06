"""Activity 相关 Schema。"""
from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class ActivityBase(BaseModel):
    title: str = Field(min_length=1, max_length=128)
    subtitle: str = ""
    category: str = Field(default="other", description="reading_share/lecture/exhibition/reading_challenge/book_drift/other")
    cover_url: str = ""
    summary: str = Field(default="", max_length=255)
    content: str = ""
    location: str = ""
    signup_start_at: datetime | None = None
    signup_end_at: datetime | None = None
    start_at: datetime
    end_at: datetime | None = None
    capacity: int = Field(default=0, ge=0, description="0 表示不限名额")
    need_certificate: bool = False
    certificate_template_id: str = ""


class ActivityCreate(ActivityBase):
    organizer_id: str = Field(default="", description="不传则取当前登录用户")


class ActivityUpdate(BaseModel):
    title: str | None = None
    subtitle: str | None = None
    category: str | None = None
    cover_url: str | None = None
    summary: str | None = None
    content: str | None = None
    location: str | None = None
    signup_start_at: datetime | None = None
    signup_end_at: datetime | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None
    capacity: int | None = None
    need_certificate: bool | None = None
    certificate_template_id: str | None = None


class ActivityOut(ORMModel, ActivityBase):
    activity_id: str
    organizer_id: str
    organizer_name: str
    signup_count: int
    checkin_count: int
    ai_copy: str
    status: str
    status_label: str = ""
    published_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class ActivityStatusChange(BaseModel):
    target_status: str = Field(description="目标状态，须符合状态机流转规则")
    reason: str = Field(default="", description="变更原因，取消活动时建议填写")
