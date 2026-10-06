"""公共依赖：分页参数、通用查询辅助。"""
from fastapi import Query

from app.core.response import CODE_PARAM_ERROR, BizError
from app.schemas.common import PageQuery


def page_query(
    page: int = Query(default=1, ge=1, description="页码，从 1 开始"),
    page_size: int = Query(default=20, ge=1, le=100, description="每页条数，最大 100"),
    keyword: str = Query(default="", description="模糊搜索关键词"),
    order_by: str = Query(default="created_at"),
    order: str = Query(default="desc", pattern="^(asc|desc)$"),
) -> PageQuery:
    if page_size > 100:
        raise BizError(CODE_PARAM_ERROR, "page_size 最大 100")
    return PageQuery(page=page, page_size=page_size, keyword=keyword, order_by=order_by, order=order)
