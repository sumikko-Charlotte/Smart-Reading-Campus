"""全局配置（智阅校园 · FastAPI 后端）。

环境变量可用 .env 覆盖，或直接使用系统环境变量。
"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # 基础信息
    APP_NAME: str = "智阅校园 Smart-Reading Campus API"
    API_V1_PREFIX: str = "/api/v1"
    DEBUG: bool = True

    # 跨域：本轮前端 PC 端本地端口 5173
    CORS_ORIGINS: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

    # 数据库：本轮先用 SQLite 跑通，切 MySQL 只需改这一行
    # 例：mysql+pymysql://user:pwd@127.0.0.1:3306/smart_reading?charset=utf8mb4
    DATABASE_URL: str = "sqlite:///./smart_reading.db"

    # 鉴权（本轮为占位实现，第 2 轮接真实 JWT）
    SECRET_KEY: str = "smart-reading-campus-dev-secret"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 12

    # 大模型（本轮只做接口占位，不真实调用）
    LLM_PROVIDER: str = "deepseek"
    LLM_MODEL: str = "deepseek-chat"
    LLM_API_BASE: str = "https://api.deepseek.com/v1"
    LLM_API_KEY: str = ""
    PROMPT_VERSION: str = "v1.0"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
