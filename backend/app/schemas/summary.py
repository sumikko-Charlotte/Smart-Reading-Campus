"""活动总结与站内推送 Schema。"""
from datetime import datetime

from pydantic import Field

from app.schemas.common import ORMModel, RequestModel


class SummaryUpsertRequest(RequestModel):
    title: str = Field(min_length=1, max_length=128)
    content: str = Field(min_length=1, description="总结正文，支持纯文本/简单 Markdown")
    images: list[str] = Field(default_factory=list, description="活动现场照片 URL，最多 9 张")


class SummaryPublishRequest(RequestModel):
    target_roles: list[str] = Field(
        default_factory=lambda: ["student", "visitor", "admin", "super_admin"],
        description="推送给哪些角色，默认全站",
    )


class SummaryOut(ORMModel):
    summary_id: str
    activity_id: str
    activity_title: str
    title: str
    content: str
    images: list[str] = Field(default_factory=list)
    author_id: str
    author_name: str
    status: str
    published_at: datetime | None = None
    view_count: int
    created_at: datetime
    updated_at: datetime


class NotificationOut(ORMModel):
    notification_id: str
    type: str
    title: str
    content: str
    ref_type: str
    ref_id: str
    # 定向消息有值，广播消息为空
    user_id: str = ""
    target_roles: list[str] = Field(default_factory=list)
    created_by_name: str
    created_at: datetime
    # 由接口按当前用户补上，不在库里存
    is_read: bool = False
    scope: str = "role"


class NotificationReadRequest(RequestModel):
    notification_ids: list[str] = Field(default_factory=list, description="留空表示全部标记已读")
