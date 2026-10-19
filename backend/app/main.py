"""智阅校园 · FastAPI 启动入口。

启动：python -m uvicorn app.main:app --reload --port 8000
文档：http://127.0.0.1:8000/docs
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.response import ok, register_exception_handlers
from app.db.base import init_db

app = FastAPI(
    title=settings.APP_NAME,
    version="2.0.0",
    description=(
        "「智阅校园」第二阶段后端（权限与角色）。\n\n"
        "- 三角色：访客 / 学生 / 管理员（普通管理员、系统管理员）\n"
        "- 权限逐项分配：`GET /users/me` 返回有效权限，接口按权限点校验\n"
        "- 活动：申办 → 提交审批 → 审批定级（校级/院级）→ 发布\n"
        "- 电子证书：服务端渲染 PDF + 公开验真\n"
        "- 统一响应体：`{code, message, data, trace_id}`；统一分页：`{list, page, page_size, total}`\n"
        "- 字段口径见 `docs/核心数据对象与统一字段规范.md`"
    ),
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)
app.include_router(api_router, prefix=settings.API_V1_PREFIX)


@app.on_event("startup")
def _startup() -> None:
    init_db()


@app.get("/api/v1/health", tags=["系统"], summary="健康检查")
def health():
    return ok(
        {
            "app": settings.APP_NAME,
            "version": "2.0.0",
            "stage": "permissions-and-roles",
            "model": settings.LLM_MODEL,
            "llm_enabled": settings.LLM_ENABLED,
            "llm_configured": settings.LLM_ENABLED and bool(settings.LLM_API_KEY),
            "prompt_version": settings.PROMPT_VERSION,
            "env": "debug" if settings.DEBUG else "prod",
            "roles": ["visitor", "student", "admin", "super_admin"],
        }
    )
