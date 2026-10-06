"""AIConversation 相关 Schema。"""
from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class ChatMessage(BaseModel):
    message_id: str = ""
    role: str = Field(description="system / user / assistant")
    content: str
    tokens: int = 0
    created_at: datetime | None = None


class ChatRequest(BaseModel):
    conversation_id: str = Field(default="", description="不传则新建会话")
    message: str = Field(min_length=1, description="本轮用户提问")
    scene: str = Field(default="qa", description="book_analysis / recommend / qa / copywriting")
    book_id: str | None = Field(default=None, description="关联图书，通用问答传 null")
    stream: bool = Field(default=False, description="是否启用 SSE 流式返回")
    model: str = Field(default="", description="不传取服务端默认模型")
    prompt_version: str = Field(default="", description="不传取服务端默认提示词版本")


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


class ChatResponse(BaseModel):
    conversation_id: str
    message: ChatMessage
    model: str
    prompt_version: str


class CopywritingRequest(BaseModel):
    topic: str = Field(min_length=1, description="活动主题/图书名")
    style: str = Field(default="xiaohongshu", description="xiaohongshu / wechat_official")
    activity_id: str = Field(default="", description="可选，关联活动时生成结果可回存 ai_copy")
