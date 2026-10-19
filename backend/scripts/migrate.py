"""执行数据库迁移（带自动备份与前后状态检查）。

用法：
    python scripts/migrate.py              # 备份 -> 升级到最新 -> 校验
    python scripts/migrate.py --status     # 只看当前版本与待执行迁移
    python scripts/migrate.py --no-backup  # 跳过备份（不建议）

之所以不直接敲 alembic：SQLite 的 DDL 不在事务里，升级中途失败会留下半成品对象，
所以强制「先备份再升级」，出问题能一条命令回滚（见 scripts/backup_db.py --restore）。
"""
import argparse
import subprocess
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from alembic.runtime.migration import MigrationContext  # noqa: E402
from alembic.script import ScriptDirectory  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.db.base import engine  # noqa: E402


def make_config() -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)
    return config


def status() -> None:
    config = make_config()
    script = ScriptDirectory.from_config(config)
    with engine.connect() as connection:
        current = MigrationContext.configure(connection).get_current_revision()
    head = script.get_current_head()
    print(f"数据库：{settings.DATABASE_URL}")
    print(f"当前版本：{current or '（空库，未初始化）'}")
    print(f"最新版本：{head}")
    if current == head:
        print("状态：已是最新 ✅")
        return
    pending = [rev.revision for rev in script.walk_revisions(head, current)] if current else []
    print(f"待执行迁移：{len(pending)} 个 -> {', '.join(reversed(pending)) or '全部'}")


def main() -> None:
    parser = argparse.ArgumentParser(description="智阅校园数据库迁移")
    parser.add_argument("--status", action="store_true", help="查看版本状态")
    parser.add_argument("--no-backup", action="store_true", help="跳过升级前备份")
    parser.add_argument("--revision", default="head", help="目标版本，默认最新")
    args = parser.parse_args()

    if args.status:
        status()
        return

    if not args.no_backup:
        result = subprocess.run(
            [sys.executable, str(BACKEND_DIR / "scripts" / "backup_db.py"), "--tag", "before_migrate"],
            cwd=BACKEND_DIR,
            capture_output=True,
            text=True,
        )
        print(result.stdout.strip() or result.stderr.strip())

    command.upgrade(make_config(), args.revision)
    print("[migrate] 升级完成")
    status()

    # 模型与库结构是否还有差异（漏了迁移脚本会在这里暴露）
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "check"], cwd=BACKEND_DIR, capture_output=True, text=True
    )
    if result.returncode == 0:
        print("[migrate] 模型与数据库结构一致 ✅")
    else:
        print("[migrate] ⚠ 模型与数据库结构存在差异，请补一条迁移：")
        print((result.stdout + result.stderr).strip()[-400:])


if __name__ == "__main__":
    main()
