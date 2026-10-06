"""ORM 模型：4 类核心对象（User / Activity / Book / AIConversation）+ 2 类派生对象。

字段口径严格对应 docs/核心数据对象与统一字段规范.md，改字段请先改规范文档。
"""
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import (
    ActivityStatus,
    BookSource,
    ConversationScene,
    ConversationStatus,
    DriftStatus,
    UserRole,
    UserStatus,
)
from app.core.security import new_id
from app.db.base import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _id(kind: str) -> Mapped[str]:
    return mapped_column(String(24), primary_key=True, default=lambda: new_id(kind))


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)


class User(Base, TimestampMixin):
    __tablename__ = "users"

    user_id: Mapped[str] = _id("user")
    student_no: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(64))
    role: Mapped[str] = mapped_column(String(16), default=UserRole.STUDENT.value, index=True)
    college: Mapped[str] = mapped_column(String(64), default="")
    major: Mapped[str] = mapped_column(String(64), default="")
    class_no: Mapped[str] = mapped_column(String(32), default="")
    grade: Mapped[str] = mapped_column(String(16), default="")
    phone: Mapped[str] = mapped_column(String(32), default="")
    email: Mapped[str] = mapped_column(String(128), default="")
    avatar_url: Mapped[str] = mapped_column(String(255), default="")
    status: Mapped[str] = mapped_column(String(16), default=UserStatus.ACTIVE.value)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Activity(Base, TimestampMixin):
    __tablename__ = "activities"

    activity_id: Mapped[str] = _id("activity")
    title: Mapped[str] = mapped_column(String(128), index=True)
    subtitle: Mapped[str] = mapped_column(String(255), default="")
    category: Mapped[str] = mapped_column(String(32), default="other", index=True)
    cover_url: Mapped[str] = mapped_column(String(255), default="")
    summary: Mapped[str] = mapped_column(String(255), default="")
    content: Mapped[str] = mapped_column(Text, default="")
    location: Mapped[str] = mapped_column(String(128), default="")
    organizer_id: Mapped[str] = mapped_column(String(24), index=True)
    organizer_name: Mapped[str] = mapped_column(String(64), default="")
    signup_start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    signup_end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    capacity: Mapped[int] = mapped_column(Integer, default=0)
    signup_count: Mapped[int] = mapped_column(Integer, default=0)
    checkin_count: Mapped[int] = mapped_column(Integer, default=0)
    need_certificate: Mapped[bool] = mapped_column(Boolean, default=False)
    certificate_template_id: Mapped[str] = mapped_column(String(24), default="")
    ai_copy: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), default=ActivityStatus.DRAFT.value, index=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Book(Base, TimestampMixin):
    __tablename__ = "books"

    book_id: Mapped[str] = _id("book")
    isbn: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(128), index=True)
    subtitle: Mapped[str] = mapped_column(String(128), default="")
    author: Mapped[str] = mapped_column(String(128), default="")
    translator: Mapped[str] = mapped_column(String(64), default="")
    publisher: Mapped[str] = mapped_column(String(128), default="")
    publish_date: Mapped[str] = mapped_column(String(16), default="")
    category: Mapped[str] = mapped_column(String(64), default="")
    language: Mapped[str] = mapped_column(String(16), default="zh-CN")
    cover_url: Mapped[str] = mapped_column(String(255), default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    tags: Mapped[list] = mapped_column(JSON, default=list)
    source: Mapped[str] = mapped_column(String(16), default=BookSource.LIBRARY.value, index=True)
    total_copies: Mapped[int] = mapped_column(Integer, default=1)
    available_copies: Mapped[int] = mapped_column(Integer, default=1)
    borrow_count: Mapped[int] = mapped_column(Integer, default=0)
    ai_summary: Mapped[str] = mapped_column(Text, default="")
    ai_tags: Mapped[list] = mapped_column(JSON, default=list)
    ai_summary_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # ---- 图书漂流扩展（source = drift 时有值）----
    drift_status: Mapped[str] = mapped_column(String(16), default=DriftStatus.IDLE.value)
    current_holder_id: Mapped[str] = mapped_column(String(24), default="")
    drift_location: Mapped[str] = mapped_column(String(128), default="")
    drift_count: Mapped[int] = mapped_column(Integer, default=0)


class AIConversation(Base, TimestampMixin):
    __tablename__ = "ai_conversations"

    conversation_id: Mapped[str] = _id("conversation")
    user_id: Mapped[str] = mapped_column(String(24), index=True)
    scene: Mapped[str] = mapped_column(String(24), default=ConversationScene.QA.value, index=True)
    title: Mapped[str] = mapped_column(String(128), default="")
    book_id: Mapped[str | None] = mapped_column(String(24), nullable=True)
    book_title: Mapped[str] = mapped_column(String(128), default="")
    model: Mapped[str] = mapped_column(String(32), default="deepseek-chat")
    messages: Mapped[list] = mapped_column(JSON, default=list)
    message_count: Mapped[int] = mapped_column(Integer, default=0)
    prompt_version: Mapped[str] = mapped_column(String(32), default="v1.0")
    status: Mapped[str] = mapped_column(String(16), default=ConversationStatus.ACTIVE.value)


# ------------------------------------------------------------ 派生对象（第 2 轮启用）


class ActivitySignup(Base, TimestampMixin):
    """活动报名与签到记录。"""

    __tablename__ = "activity_signups"

    signup_id: Mapped[str] = _id("signup")
    activity_id: Mapped[str] = mapped_column(String(24), index=True)
    user_id: Mapped[str] = mapped_column(String(24), index=True)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    signed_up_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    checked_in_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    certificate_no: Mapped[str] = mapped_column(String(32), default="")


class DriftRecord(Base, TimestampMixin):
    """图书漂流流转记录。"""

    __tablename__ = "drift_records"

    drift_id: Mapped[str] = _id("drift")
    book_id: Mapped[str] = mapped_column(String(24), index=True)
    holder_id: Mapped[str] = mapped_column(String(24), index=True)
    from_user_id: Mapped[str] = mapped_column(String(24), default="")
    status: Mapped[str] = mapped_column(String(16), default=DriftStatus.IDLE.value)
    location: Mapped[str] = mapped_column(String(128), default="")
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
