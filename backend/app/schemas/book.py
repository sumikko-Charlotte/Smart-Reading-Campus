"""Book 相关 Schema。"""
from datetime import datetime

from pydantic import BaseModel, Field, field_serializer, field_validator, model_validator

from app.schemas.common import ORMModel, RequestModel


class BookBase(RequestModel):
    isbn: str = Field(default="", max_length=20, description="去连字符的 ISBN；无 ISBN 时允许空字符串")
    title: str = Field(min_length=1, max_length=128)
    subtitle: str = ""
    author: str = ""
    translator: str = ""
    publisher: str = ""
    publish_date: str | None = Field(default=None, description="YYYY-MM-DD")
    category: str = ""
    language: str = "zh-CN"
    cover_url: str = ""
    summary: str = ""
    tags: list[str] = Field(default_factory=list)
    source: str = Field(default="library", description="library / drift / both，由服务端维护")
    total_copies: int = 1
    available_copies: int = 1
    borrow_count: int = 0


class BookCreate(RequestModel):
    isbn: str = Field(default="", max_length=20, description="去连字符的 ISBN；无 ISBN 时允许空字符串")
    title: str = Field(min_length=1, max_length=128)
    subtitle: str = ""
    author: str = ""
    translator: str = ""
    publisher: str = ""
    publish_date: str | None = None
    category: str = ""
    language: str = "zh-CN"
    cover_url: str = ""
    summary: str = ""
    tags: list[str] = Field(default_factory=list)
    total_copies: int = Field(default=0, ge=0)
    available_copies: int = Field(default=0, ge=0)
    # ---- 馆藏扩展（第二轮②）：AI 录书写入、前端展示「去哪找这本书」----
    clc_code: str = Field(default="", max_length=32, description="中图法分类号，如 TP181")
    call_no: str = Field(default="", max_length=64, description="索书号")
    publisher_place: str = ""
    pages: int = Field(default=0, ge=0)
    price: float = Field(default=0, ge=0)
    binding: str = ""
    toc: str = ""
    lib_location: str = Field(default="", max_length=64, description="馆藏地")

    @field_validator("isbn")
    @classmethod
    def normalize_isbn(cls, value: str) -> str:
        return value.replace("-", "").replace(" ", "").strip()

    @field_validator("publish_date")
    @classmethod
    def validate_publish_date(cls, value: str | None) -> str | None:
        if value is not None:
            datetime.strptime(value, "%Y-%m-%d")
        return value

    @model_validator(mode="after")
    def validate_copy_counts(self):
        if self.available_copies > self.total_copies:
            raise ValueError("available_copies 不得大于 total_copies")
        return self


class BookUpdate(RequestModel):
    title: str | None = None
    subtitle: str | None = None
    author: str | None = None
    translator: str | None = None
    publisher: str | None = None
    publish_date: str | None = None
    category: str | None = None
    language: str | None = None
    cover_url: str | None = None
    summary: str | None = None
    tags: list[str] | None = None
    total_copies: int | None = Field(default=None, ge=0)
    available_copies: int | None = Field(default=None, ge=0)
    clc_code: str | None = None
    call_no: str | None = None
    publisher_place: str | None = None
    pages: int | None = Field(default=None, ge=0)
    price: float | None = Field(default=None, ge=0)
    binding: str | None = None
    toc: str | None = None
    lib_location: str | None = None


class BookOut(ORMModel, BookBase):
    book_id: str
    clc_code: str = ""
    call_no: str = ""
    publisher_place: str = ""
    pages: int = 0
    price: float = 0
    binding: str = ""
    toc: str = ""
    lib_location: str = ""
    ai_summary: str
    ai_tags: list[str]
    ai_summary_updated_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    @field_validator("publish_date", mode="before")
    @classmethod
    def normalize_empty_publish_date(cls, value: str | None) -> str | None:
        return None if value == "" else value


class RecommendRequest(RequestModel):
    scene: str = Field(default="recommend", description="recommend / book_analysis")
    limit: int = Field(default=6, ge=1, le=20)
    extra_prompt: str = Field(default="", description="补充偏好，如「偏计算机类、篇幅不要太长」")


class RecommendItem(BaseModel):
    book: BookOut
    reason: str = Field(description="AI 给出的推荐理由")


class RecommendResponse(RequestModel):
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
