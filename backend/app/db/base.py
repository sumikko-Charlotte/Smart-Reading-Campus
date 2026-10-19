"""SQLAlchemy 引擎与会话。本轮用 SQLite，切 MySQL 只改 config.DATABASE_URL。"""
from collections.abc import Generator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings

connect_args = {"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(settings.DATABASE_URL, echo=False, future=True, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _ensure_columns(connection, table: str, columns: dict[str, str]) -> list[str]:
    """轻量迁移：缺列就 ALTER TABLE ADD COLUMN（SQLite 只支持加列，够本项目用）。"""
    existing = {column["name"] for column in inspect(engine).get_columns(table)}
    added: list[str] = []
    for name, ddl in columns.items():
        if name in existing:
            continue
        connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))
        added.append(name)
    return added


def init_db() -> None:
    from app.db import models  # noqa: F401  确保模型已注册

    Base.metadata.create_all(bind=engine)
    if engine.dialect.name == "sqlite":
        with engine.begin() as connection:
            # ---- 第二阶段的增量列（权限 / 审批定级）----
            _ensure_columns(
                connection,
                "users",
                {
                    "granted_permissions": "TEXT NOT NULL DEFAULT '[]'",
                    "revoked_permissions": "TEXT NOT NULL DEFAULT '[]'",
                },
            )
            _ensure_columns(
                connection,
                "activities",
                {
                    "level": "VARCHAR(16) NOT NULL DEFAULT 'none'",
                    "submitted_at": "DATETIME",
                    "reviewed_by": "VARCHAR(24) NOT NULL DEFAULT ''",
                    "reviewed_by_name": "VARCHAR(64) NOT NULL DEFAULT ''",
                    "reviewed_at": "DATETIME",
                    "review_comment": "VARCHAR(255) NOT NULL DEFAULT ''",
                },
            )
            # 旧角色 librarian 并入普通管理员（第二阶段只有 3 类角色）
            connection.execute(text("UPDATE users SET role = 'admin' WHERE role = 'librarian'"))
            columns = {column["name"] for column in inspect(engine).get_columns("drift_records")}
            if "status" in columns and "drift_status" not in columns:
                connection.execute(
                    text(
                        "CREATE TABLE drift_records_v2 ("
                        "drift_id VARCHAR(24) NOT NULL PRIMARY KEY, book_id VARCHAR(24) NOT NULL, "
                        "drift_status VARCHAR(16) NOT NULL, current_holder_id VARCHAR(24), "
                        "drift_location VARCHAR(128) NOT NULL DEFAULT '', drift_count INTEGER NOT NULL DEFAULT 0, "
                        "created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL, is_deleted BOOLEAN NOT NULL, "
                        "legacy_from_user_id VARCHAR(24) DEFAULT '', legacy_claimed_at DATETIME)"
                    )
                )
                connection.execute(
                    text(
                        "INSERT INTO drift_records_v2 "
                        "(drift_id, book_id, drift_status, current_holder_id, drift_location, drift_count, "
                        "created_at, updated_at, is_deleted, legacy_from_user_id, legacy_claimed_at) "
                        "SELECT drift_id, book_id, status, holder_id, location, 0, created_at, updated_at, "
                        "is_deleted, from_user_id, claimed_at FROM drift_records"
                    )
                )
                connection.execute(text("DROP TABLE drift_records"))
                connection.execute(text("ALTER TABLE drift_records_v2 RENAME TO drift_records"))
                connection.execute(text("CREATE INDEX ix_drift_records_book_id ON drift_records (book_id)"))
                connection.execute(text("CREATE INDEX ix_drift_records_drift_status ON drift_records (drift_status)"))
                connection.execute(text("CREATE INDEX ix_drift_records_current_holder_id ON drift_records (current_holder_id)"))
            connection.execute(
                text("CREATE UNIQUE INDEX IF NOT EXISTS uq_activity_signup_user ON activity_signups (activity_id, user_id)")
            )
            connection.execute(
                text("CREATE TABLE IF NOT EXISTS schema_migrations (version VARCHAR(64) NOT NULL PRIMARY KEY)")
            )
            migration_version = "20261007_utc_activity_times"
            applied = connection.execute(
                text("SELECT 1 FROM schema_migrations WHERE version = :version"),
                {"version": migration_version},
            ).first()
            if applied is None:
                for column in ("signup_start_at", "signup_end_at", "start_at", "end_at"):
                    connection.execute(text(f"UPDATE activities SET {column} = datetime({column}, '-8 hours') WHERE {column} IS NOT NULL"))
                connection.execute(
                    text("INSERT INTO schema_migrations (version) VALUES (:version)"),
                    {"version": migration_version},
                )
            book_columns = {column["name"] for column in inspect(engine).get_columns("books")}
            if "drift_status" in book_columns:
                connection.execute(
                    text(
                        "CREATE TABLE books_v2 ("
                        "book_id VARCHAR(24) NOT NULL PRIMARY KEY, isbn VARCHAR(20) NOT NULL DEFAULT '', "
                        "title VARCHAR(128) NOT NULL, subtitle VARCHAR(128) NOT NULL DEFAULT '', "
                        "author VARCHAR(128) NOT NULL DEFAULT '', translator VARCHAR(64) NOT NULL DEFAULT '', "
                        "publisher VARCHAR(128) NOT NULL DEFAULT '', publish_date VARCHAR(16), "
                        "category VARCHAR(64) NOT NULL DEFAULT '', language VARCHAR(16) NOT NULL DEFAULT 'zh-CN', "
                        "cover_url VARCHAR(255) NOT NULL DEFAULT '', summary TEXT NOT NULL DEFAULT '', "
                        "tags JSON NOT NULL, source VARCHAR(16) NOT NULL, total_copies INTEGER NOT NULL DEFAULT 0, "
                        "available_copies INTEGER NOT NULL DEFAULT 0, borrow_count INTEGER NOT NULL DEFAULT 0, "
                        "ai_summary TEXT NOT NULL DEFAULT '', ai_tags JSON NOT NULL, ai_summary_updated_at DATETIME, "
                        "created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL, is_deleted BOOLEAN NOT NULL)"
                    )
                )
                connection.execute(
                    text(
                        "INSERT INTO books_v2 (book_id, isbn, title, subtitle, author, translator, publisher, publish_date, "
                        "category, language, cover_url, summary, tags, source, total_copies, available_copies, borrow_count, "
                        "ai_summary, ai_tags, ai_summary_updated_at, created_at, updated_at, is_deleted) "
                        "SELECT book_id, isbn, title, subtitle, author, translator, publisher, NULLIF(publish_date, ''), "
                        "category, language, cover_url, summary, tags, source, total_copies, available_copies, borrow_count, "
                        "ai_summary, ai_tags, ai_summary_updated_at, created_at, updated_at, is_deleted FROM books"
                    )
                )
                connection.execute(
                    text(
                        "INSERT INTO drift_records (drift_id, book_id, drift_status, current_holder_id, drift_location, "
                        "drift_count, created_at, updated_at, is_deleted) "
                        "SELECT 'drf_' || lower(substr(hex(randomblob(6)), 1, 12)), b.book_id, b.drift_status, "
                        "NULLIF(b.current_holder_id, ''), b.drift_location, b.drift_count, b.created_at, b.updated_at, b.is_deleted "
                        "FROM books b WHERE b.source IN ('drift', 'both') AND b.drift_status != 'closed' "
                        "AND NOT EXISTS (SELECT 1 FROM drift_records d WHERE d.book_id = b.book_id AND d.is_deleted = 0)"
                    )
                )
                connection.execute(text("DROP TABLE books"))
                connection.execute(text("ALTER TABLE books_v2 RENAME TO books"))
                connection.execute(text("CREATE INDEX ix_books_isbn ON books (isbn)"))
                connection.execute(text("CREATE INDEX ix_books_title ON books (title)"))
                connection.execute(text("CREATE INDEX ix_books_source ON books (source)"))
