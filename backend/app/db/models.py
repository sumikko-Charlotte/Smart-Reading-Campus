"""ORM 模型：4 类核心对象 + 派生对象（第 2 阶段：权限、证书、总结、推送）。

字段口径对应 docs/核心数据对象与统一字段规范.md 与 docs/第2阶段-权限与角色设计.md，
改字段请先改文档。
"""
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import (
    ActivityLevel,
    ActivityStatus,
    BookSource,
    CertificateStatus,
    ConversationScene,
    ConversationStatus,
    DriftStatus,
    SummaryStatus,
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
    # 权限分配：角色给默认值，这里存「额外授予」和「显式收回」，见 core/permissions.py
    granted_permissions: Mapped[list] = mapped_column(JSON, default=list)
    revoked_permissions: Mapped[list] = mapped_column(JSON, default=list)
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
    # 审批与定级
    level: Mapped[str] = mapped_column(String(16), default=ActivityLevel.NONE.value, index=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_by: Mapped[str] = mapped_column(String(24), default="")
    reviewed_by_name: Mapped[str] = mapped_column(String(64), default="")
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_comment: Mapped[str] = mapped_column(String(255), default="")
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Book(Base, TimestampMixin):
    __tablename__ = "books"

    book_id: Mapped[str] = _id("book")
    isbn: Mapped[str] = mapped_column(String(20), default="", index=True)
    title: Mapped[str] = mapped_column(String(128), index=True)
    subtitle: Mapped[str] = mapped_column(String(128), default="")
    author: Mapped[str] = mapped_column(String(128), default="")
    translator: Mapped[str] = mapped_column(String(64), default="")
    publisher: Mapped[str] = mapped_column(String(128), default="")
    publish_date: Mapped[str | None] = mapped_column(String(16), nullable=True)
    category: Mapped[str] = mapped_column(String(64), default="")
    language: Mapped[str] = mapped_column(String(16), default="zh-CN")
    cover_url: Mapped[str] = mapped_column(String(255), default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    tags: Mapped[list] = mapped_column(JSON, default=list)
    source: Mapped[str] = mapped_column(String(16), default=BookSource.LIBRARY.value, index=True)
    total_copies: Mapped[int] = mapped_column(Integer, default=0)
    available_copies: Mapped[int] = mapped_column(Integer, default=0)
    borrow_count: Mapped[int] = mapped_column(Integer, default=0)
    ai_summary: Mapped[str] = mapped_column(Text, default="")
    ai_tags: Mapped[list] = mapped_column(JSON, default=list)
    ai_summary_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


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


# ------------------------------------------------------------ 派生对象


class ActivitySignup(Base, TimestampMixin):
    """活动报名与签到记录。"""

    __tablename__ = "activity_signups"
    __table_args__ = (UniqueConstraint("activity_id", "user_id", name="uq_activity_signup_user"),)

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
    drift_status: Mapped[str] = mapped_column(String(16), default=DriftStatus.IDLE.value, index=True)
    current_holder_id: Mapped[str | None] = mapped_column(String(24), nullable=True, index=True)
    drift_location: Mapped[str] = mapped_column(String(128), default="")
    drift_count: Mapped[int] = mapped_column(Integer, default=0)


class Certificate(Base, TimestampMixin):
    """电子证书：一人一活动一张，PDF 由服务端按模板渲染。"""

    __tablename__ = "certificates"
    __table_args__ = (UniqueConstraint("activity_id", "user_id", name="uq_certificate_activity_user"),)

    certificate_id: Mapped[str] = _id("certificate")
    serial_no: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    verify_code: Mapped[str] = mapped_column(String(16), unique=True, index=True)

    user_id: Mapped[str] = mapped_column(String(24), index=True)
    student_name: Mapped[str] = mapped_column(String(64))
    student_no: Mapped[str] = mapped_column(String(32), default="")
    college: Mapped[str] = mapped_column(String(64), default="")

    activity_id: Mapped[str] = mapped_column(String(24), index=True)
    activity_title: Mapped[str] = mapped_column(String(128), default="")
    activity_level: Mapped[str] = mapped_column(String(16), default=ActivityLevel.NONE.value)
    certificate_name: Mapped[str] = mapped_column(String(64), default="荣誉证书")

    seal_name: Mapped[str] = mapped_column(String(64), default="北京邮电大学图书馆")
    issued_by: Mapped[str] = mapped_column(String(24), default="")
    issued_by_name: Mapped[str] = mapped_column(String(64), default="")
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    status: Mapped[str] = mapped_column(String(16), default=CertificateStatus.ISSUED.value, index=True)


class ActivitySummary(Base, TimestampMixin):
    """活动总结：活动结束后由主办方撰写，发布后进入推送流。"""

    __tablename__ = "activity_summaries"

    summary_id: Mapped[str] = _id("summary")
    activity_id: Mapped[str] = mapped_column(String(24), index=True)
    activity_title: Mapped[str] = mapped_column(String(128), default="")
    title: Mapped[str] = mapped_column(String(128), default="")
    content: Mapped[str] = mapped_column(Text, default="")
    images: Mapped[list] = mapped_column(JSON, default=list)
    author_id: Mapped[str] = mapped_column(String(24), default="")
    author_name: Mapped[str] = mapped_column(String(64), default="")
    status: Mapped[str] = mapped_column(String(16), default=SummaryStatus.DRAFT.value, index=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    view_count: Mapped[int] = mapped_column(Integer, default=0)


class Notification(Base, TimestampMixin):
    """站内推送：target_roles 决定哪些角色能看到（访客也在此列）。"""

    __tablename__ = "notifications"

    notification_id: Mapped[str] = _id("notification")
    type: Mapped[str] = mapped_column(String(32), default="system", index=True)
    title: Mapped[str] = mapped_column(String(128))
    content: Mapped[str] = mapped_column(Text, default="")
    ref_type: Mapped[str] = mapped_column(String(24), default="")
    ref_id: Mapped[str] = mapped_column(String(24), default="")
    target_roles: Mapped[list] = mapped_column(JSON, default=list)
    created_by: Mapped[str] = mapped_column(String(24), default="")
    created_by_name: Mapped[str] = mapped_column(String(64), default="")


class PermissionLog(Base, TimestampMixin):
    """权限变更审计：谁、在什么时候、给谁、加了/减了什么权限。"""

    __tablename__ = "permission_logs"

    log_id: Mapped[str] = _id("permission_log")
    operator_id: Mapped[str] = mapped_column(String(24), index=True)
    operator_name: Mapped[str] = mapped_column(String(64), default="")
    target_user_id: Mapped[str] = mapped_column(String(24), index=True)
    target_user_name: Mapped[str] = mapped_column(String(64), default="")
    action: Mapped[str] = mapped_column(String(16))  # grant / revoke / role_change
    permission: Mapped[str] = mapped_column(String(48), default="")
    before_value: Mapped[str] = mapped_column(String(64), default="")
    after_value: Mapped[str] = mapped_column(String(64), default="")
    remark: Mapped[str] = mapped_column(String(255), default="")
