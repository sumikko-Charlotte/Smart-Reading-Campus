"""AIConversation 相关 Schema。"""
from datetime import datetime, timedelta, timezone

from pydantic import BaseModel, Field, field_serializer

from app.schemas.common import ORMModel, RequestModel


class ChatMessage(BaseModel):
    message_id: str = ""
    role: str = Field(description="system / user / assistant")
    content: str
    tokens: int = 0
    created_at: datetime | None = None

    @field_serializer("created_at")
    def serialize_created_at(self, value):
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone(timedelta(hours=8))).isoformat()


class ChatRequest(RequestModel):
    conversation_id: str | None = Field(default=None, description="不传或传 null 时新建会话")
    scene: str = Field(default="qa", description="book_analysis / recommend / qa / copywriting")
    content: str = Field(min_length=1, description="本轮用户提问")
    book_id: str | None = Field(default=None, description="关联图书，通用问答传 null")
    stream: bool = Field(default=False, description="是否启用 SSE 流式返回")


class ConversationOut(ORMModel):
    conversation_id: str
    user_id: str
    scene: str
    title: str
    book_id: str | None = None
    book_title: str
    model: str
    messages: list[ChatMessage]
    message_count: int
    prompt_version: str
    status: str
    created_at: datetime
    updated_at: datetime


class ConversationBrief(ORMModel):
    conversation_id: str
    scene: str
    title: str
    book_title: str
    message_count: int
    status: str
    updated_at: datetime


class ChatResponse(RequestModel):
    conversation_id: str
    message_id: str
    content: str


class CopywritingRequest(RequestModel):
    topic: str = Field(min_length=1, description="活动主题/图书名")
    style: str = Field(default="xiaohongshu", description="xiaohongshu / wechat_official")
    activity_id: str = Field(default="", description="可选，关联活动时生成结果可回存 ai_copy")
