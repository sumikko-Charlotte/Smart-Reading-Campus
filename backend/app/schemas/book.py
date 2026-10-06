"""Book 相关 Schema。"""
from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class BookBase(BaseModel):
    isbn: str = Field(min_length=10, max_length=20, description="去连字符的 ISBN，扫码入口唯一键")
    title: str = Field(min_length=1, max_length=128)
    subtitle: str = ""
    author: str = ""
    translator: str = ""
    publisher: str = ""
    publish_date: str = Field(default="", description="YYYY-MM-DD")
    category: str = ""
    language: str = "zh-CN"
    cover_url: str = ""
    summary: str = ""
    tags: list[str] = Field(default_factory=list)
    source: str = Field(default="library", description="library / drift")
    total_copies: int = 1
    available_copies: int = 1
    borrow_count: int = 0


class BookCreate(BookBase):
    pass


class BookUpdate(BaseModel):
    title: str | None = None
    author: str | None = None
    publisher: str | None = None
    category: str | None = None
    cover_url: str | None = None
    summary: str | None = None
    tags: list[str] | None = None
    total_copies: int | None = None
    available_copies: int | None = None


class BookOut(ORMModel, BookBase):
    book_id: str
    ai_summary: str
    ai_tags: list[str]
    ai_summary_updated_at: datetime | None = None
    drift_status: str = "idle"
    current_holder_id: str = ""
    drift_location: str = ""
    drift_count: int = 0
    created_at: datetime
    updated_at: datetime


class RecommendRequest(BaseModel):
    user_id: str = Field(default="", description="不传取当前登录用户")
    scene: str = Field(default="recommend", description="recommend / book_analysis")
    limit: int = Field(default=6, ge=1, le=20)
    extra_prompt: str = Field(default="", description="补充偏好，如「偏计算机类、篇幅不要太长」")


class RecommendItem(BaseModel):
    book: BookOut
    reason: str = Field(description="AI 给出的推荐理由")


class RecommendResponse(BaseModel):
    conversation_id: str
    items: list[RecommendItem]
    model: str
    prompt_version: str


class BookAnalysisResponse(BaseModel):
    book_id: str
    ai_summary: str
    ai_tags: list[str]
    cached: bool = Field(description="是否命中已有解读")
    conversation_id: str
    model: str
    prompt_version: str
