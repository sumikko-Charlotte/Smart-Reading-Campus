"""SQLAlchemy 引擎与会话。本轮用 SQLite，切 MySQL 只改 config.DATABASE_URL。

表结构变更统一由 Alembic 管理（backend/alembic/versions/）：
- 全新库：按模型建表后立即 stamp 到最新版本，避免后续迁移重复建表
- 已有库：升级到 head
第 2 阶段起不再用「缺列就 ALTER」的手工补丁，历史补丁已收纳进基线迁移。
"""
from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings

connect_args = {"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(settings.DATABASE_URL, echo=False, future=True, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

_BACKEND_DIR = Path(__file__).resolve().parents[2]


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def alembic_config():
    """构造 Alembic 配置：脚本目录固定在 backend/alembic，连接串由 env.py 从 settings 取。"""
    from alembic.config import Config

    ini_path = _BACKEND_DIR / "alembic.ini"
    config = Config(str(ini_path))
    config.set_main_option("script_location", str(_BACKEND_DIR / "alembic"))
    config.attributes["configure_logger"] = False  # 复用应用的日志配置
    return config


def init_db() -> None:
    """启动时准备数据库：新库建表 + 打版本，旧库升级到最新。"""
    from alembic import command

    from app.db import models  # noqa: F401  确保模型已注册

    if not inspect(engine).get_table_names():
        Base.metadata.create_all(bind=engine)
        command.stamp(alembic_config(), "head")
        return
    command.upgrade(alembic_config(), "head")
