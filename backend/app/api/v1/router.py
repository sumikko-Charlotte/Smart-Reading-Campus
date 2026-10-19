"""v1 路由汇总。"""
from fastapi import APIRouter

from app.api.v1 import activity, ai, book, certificate, drift, permission, summary, user

api_router = APIRouter()
api_router.include_router(user.router)
api_router.include_router(permission.router)
api_router.include_router(activity.router)
api_router.include_router(book.router)
api_router.include_router(ai.router)
api_router.include_router(drift.router)
api_router.include_router(certificate.router)
api_router.include_router(summary.router)
