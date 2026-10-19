"""全局配置（智阅校园 · FastAPI 后端）。

环境变量可用 backend/.env 覆盖，或直接使用系统环境变量。
无论从仓库根目录还是 backend/ 启动，都读取同一份配置。
"""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

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
    # 绝对路径：避免从仓库根目录 / backend/ 启动时落到两个不同的库文件
    DATABASE_URL: str = f"sqlite:///{(_BACKEND_DIR / 'smart_reading.db').as_posix()}"

    # 鉴权（本轮为占位实现，第 2 轮接真实 JWT）
    SECRET_KEY: str = "smart-reading-campus-dev-secret"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 12

    # 大模型：填写 LLM_API_KEY 后默认启用；设为 false 可紧急关闭以免扣费
    LLM_ENABLED: bool = True
    # provider 只影响默认 base_url 的推断与错误提示，实际都走 OpenAI 兼容协议：
    #   deepseek  https://api.deepseek.com/v1
    #   aliyun    阿里云百炼 MaaS 工作空间（需填 LLM_API_BASE）
    #   openai    https://api.openai.com/v1
    #   ollama    本地 http://127.0.0.1:11434/v1（无需 key）
    #   qwen      https://dashscope.aliyuncs.com/compatible-mode/v1
    LLM_PROVIDER: str = "deepseek"
    LLM_MODEL: str = "deepseek-chat"
    LLM_API_BASE: str = "https://api.deepseek.com/v1"
    LLM_API_KEY: str = ""
    LLM_MAX_TOKENS: int = 1024
    PROMPT_VERSION: str = "v1.0"
    # 智能体运行时：超时、重试写在这里，避免散落在各处
    LLM_TIMEOUT_SEC: float = 45.0
    LLM_RETRY: int = 1
    LLM_TEMPERATURE: float = 0.3
    # 智能体单次运行最多几步工具调用；步数越多越慢越贵，4 步覆盖本项目所有场景
    AGENT_MAX_STEPS: int = 4
    # 单次运行的 token 预算，超出即停止并输出已有结论
    AGENT_TOKEN_BUDGET: int = 6000
    # 是否允许工具调用；关掉后所有场景退回单轮生成（仍可用，只是不再自己查库）
    AGENT_TOOLS_ENABLED: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
