"""Activity 相关 Schema。"""
from datetime import datetime, timezone
from typing import Literal

from pydantic import Field, model_validator

from app.schemas.common import ORMModel, RequestModel


def _normalize_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        raise ValueError("时间必须包含时区偏移")
    return value.astimezone(timezone.utc)


class ActivityBase(RequestModel):
    title: str = Field(min_length=1, max_length=128)
    subtitle: str = ""
    category: Literal["reading_share", "lecture", "exhibition", "reading_challenge", "book_drift", "other"] = "other"
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
    @model_validator(mode="after")
    def validate_time_range(self):
        for field_name in ("signup_start_at", "signup_end_at", "start_at", "end_at"):
            setattr(self, field_name, _normalize_datetime(getattr(self, field_name)))
        if self.end_at is not None and self.end_at <= self.start_at:
            raise ValueError("end_at 必须晚于 start_at")
        if self.signup_start_at is not None and self.signup_end_at is not None and self.signup_start_at >= self.signup_end_at:
            raise ValueError("signup_start_at 必须早于 signup_end_at")
        if self.signup_end_at is not None and self.signup_end_at > self.start_at:
            raise ValueError("signup_end_at 不得晚于 start_at")
        return self


class ActivityUpdate(RequestModel):
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
    capacity: int | None = Field(default=None, ge=0)
    need_certificate: bool | None = None
    certificate_template_id: str | None = None

    @model_validator(mode="after")
    def normalize_datetimes(self):
        for field_name in ("signup_start_at", "signup_end_at", "start_at", "end_at"):
            value = getattr(self, field_name)
            if value is not None:
                setattr(self, field_name, _normalize_datetime(value))
        return self


class ActivityOut(ORMModel, ActivityBase):
    activity_id: str
    organizer_id: str
    organizer_name: str
    signup_count: int
    checkin_count: int
    ai_copy: str
    status: str
    published_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class ActivityStatusChange(RequestModel):
    target_status: Literal["draft", "published", "signup_closed", "ongoing", "finished", "cancelled"] = Field(
        description="目标状态，须符合状态机流转规则"
    )
    reason: str = Field(default="", description="变更原因，取消活动时建议填写")


class EmptyPayload(RequestModel):
    pass


class ActivitySignupOut(ORMModel):
    signup_id: str
    activity_id: str
    user_id: str
    status: str
    signed_up_at: datetime
    checked_in_at: datetime | None = None
    certificate_no: str
    created_at: datetime
    updated_at: datetime


class ActivitySignupView(ActivitySignupOut):
    name: str
    student_no: str
