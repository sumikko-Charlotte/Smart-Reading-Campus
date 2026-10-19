"""数据库备份 / 恢复（本地 SQLite -> backend/backups/）。

用法：
    python scripts/backup_db.py                 # 备份一份
    python scripts/backup_db.py --keep 10       # 备份并只保留最近 10 份
    python scripts/backup_db.py --list          # 列出已有备份
    python scripts/backup_db.py --restore x.db  # 用指定备份覆盖当前库（会先自动备份当前库）

要点：
- 用 SQLite 的 `VACUUM INTO` 做快照，比直接复制文件安全（能拿到一致性视图）。
- 备份文件带时间戳，默认保留 20 份，避免本地堆积。
- 恢复前会把当前库再备份一次，防止误操作不可逆。
"""
import argparse
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import settings  # noqa: E402

BACKUP_DIR = BACKEND_DIR / "backups"


def db_path() -> Path:
    if not settings.DATABASE_URL.startswith("sqlite"):
        raise SystemExit("当前 DATABASE_URL 不是 SQLite，请用 mysqldump / pg_dump 备份。")
    return Path(settings.DATABASE_URL.replace("sqlite:///", ""))


def backup(tag: str = "") -> Path:
    source = db_path()
    if not source.exists():
        raise SystemExit(f"数据库不存在：{source}")
    BACKUP_DIR.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target = BACKUP_DIR / f"smart_reading_{stamp}{('_' + tag) if tag else ''}.db"
    con = sqlite3.connect(source)
    try:
        con.execute("VACUUM INTO ?", (str(target),))
    finally:
        con.close()
    size_mb = target.stat().st_size / 1024 / 1024
    print(f"[backup] 已备份 -> {target.relative_to(BACKEND_DIR)}（{size_mb:.2f} MB）")
    return target


def prune(keep: int) -> None:
    files = sorted(BACKUP_DIR.glob("smart_reading_*.db"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in files[keep:]:
        old.unlink()
        print(f"[backup] 清理旧备份 {old.name}")


def list_backups() -> None:
    files = sorted(BACKUP_DIR.glob("smart_reading_*.db"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        print("[backup] 暂无备份")
        return
    for item in files:
        stat = item.stat()
        print(f"  {item.name:42s} {stat.st_size / 1024 / 1024:6.2f} MB  "
              f"{datetime.fromtimestamp(stat.st_mtime):%Y-%m-%d %H:%M}")


def restore(name: str) -> None:
    candidate = Path(name)
    if not candidate.is_absolute():
        candidate = BACKUP_DIR / candidate if (BACKUP_DIR / name).exists() else Path(name)
    if not candidate.exists():
        raise SystemExit(f"找不到备份文件：{name}")

    backup(tag="before_restore")  # 恢复前先保底
    target = db_path()
    for suffix in ("", "-wal", "-shm"):  # 清掉 SQLite 的旁挂文件，避免回滚到旧数据
        side = Path(str(target) + suffix)
        if side.exists():
            side.unlink()
    shutil.copy2(candidate, target)
    print(f"[backup] 已用 {candidate.name} 覆盖当前库 {target}")


def main() -> None:
    parser = argparse.ArgumentParser(description="智阅校园本地数据库备份工具")
    parser.add_argument("--keep", type=int, default=20, help="保留最近 N 份备份")
    parser.add_argument("--list", action="store_true", help="列出已有备份")
    parser.add_argument("--restore", metavar="FILE", help="用指定备份恢复")
    parser.add_argument("--tag", default="", help="给备份加标签，如 before_migrate")
    args = parser.parse_args()

    if args.list:
        list_backups()
        return
    if args.restore:
        restore(args.restore)
        return
    backup(args.tag)
    prune(args.keep)


if __name__ == "__main__":
    main()
