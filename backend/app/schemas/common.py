"""Pydantic Schema：接口层数据契约（与 docs/核心数据对象与统一字段规范.md 一一对应）。"""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class PageQuery(BaseModel):
    page: int = Field(default=1, ge=1, description="页码，从 1 开始")
    page_size: int = Field(default=20, ge=1, le=100, description="每页条数，最大 100")
    keyword: str = Field(default="", description="模糊搜索关键词")
    order_by: str = Field(default="created_at", description="排序字段")
    order: Literal["asc", "desc"] = Field(default="desc", description="排序方向")
