"""统一响应体、分页模型与异常处理。

设计目标：双端拿到的手感完全一致——永远是 {code, message, data, trace_id}。
"""
import uuid
from typing import Any, Generic, List, TypeVar

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

T = TypeVar("T")

# 错误码表：与《核心数据对象与统一字段规范》1.6 节保持一致
CODE_OK = 0
CODE_PARAM_ERROR = 1001
CODE_UNAUTHORIZED = 1002
CODE_FORBIDDEN = 1003
CODE_NOT_FOUND = 1004
CODE_ILLEGAL_STATE = 1005
CODE_SERVER_ERROR = 5000


def new_trace_id() -> str:
    return uuid.uuid4().hex[:12]


class ApiResponse(BaseModel, Generic[T]):
    code: int = CODE_OK
    message: str = "ok"
    data: T | None = None
    trace_id: str = Field(default_factory=new_trace_id)


class PageMeta(BaseModel):
    page: int = 1
    page_size: int = 20
    total: int = 0


class PageData(BaseModel, Generic[T]):
    """分页数据体（字段名 list 与规范一致；用 typing.List 避免与内建 list 冲突）"""

    list: List[T] = Field(default_factory=list)
    page: int = 1
    page_size: int = 20
    total: int = 0


class BizError(Exception):
    """业务异常：抛出后由统一异常处理器包装成标准响应。"""

    def __init__(self, code: int, message: str, http_status: int = status.HTTP_200_OK):
        self.code = code
        self.message = message
        self.http_status = http_status
        super().__init__(message)


def ok(data: Any = None, message: str = "ok") -> dict:
    return {"code": CODE_OK, "message": message, "data": data, "trace_id": new_trace_id()}


def page_result(items: list, page: int, page_size: int, total: int) -> dict:
    return {"list": items, "page": page, "page_size": page_size, "total": total}


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(BizError)
    async def _biz_error(_: Request, exc: BizError):
        return JSONResponse(
            status_code=exc.http_status,
            content={"code": exc.code, "message": exc.message, "data": None, "trace_id": new_trace_id()},
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError):
        first = exc.errors()[0] if exc.errors() else {}
        loc = ".".join(str(x) for x in first.get("loc", []) if x != "body")
        msg = f"参数校验失败：{loc} {first.get('msg', '')}".strip()
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"code": CODE_PARAM_ERROR, "message": msg, "data": None, "trace_id": new_trace_id()},
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException):
        code = {401: CODE_UNAUTHORIZED, 403: CODE_FORBIDDEN, 404: CODE_NOT_FOUND}.get(exc.status_code, CODE_SERVER_ERROR)
        return JSONResponse(
            status_code=exc.status_code,
            content={"code": code, "message": str(exc.detail), "data": None, "trace_id": new_trace_id()},
        )

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception):
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"code": CODE_SERVER_ERROR, "message": f"服务器内部错误：{exc}", "data": None, "trace_id": new_trace_id()},
        )
