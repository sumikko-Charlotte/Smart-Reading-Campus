"""学校脱敏数据导入：学生 / 书目 / 借阅。

用法示例：
    # 1) 学生基础信息（学院、专业、年级、班级；姓名可不提供）
    python scripts/import_school_data.py --students 学生名单.csv --dry-run
    python scripts/import_school_data.py --students 学生名单.csv

    # 2) 馆藏书目
    python scripts/import_school_data.py --books 书目.csv

    # 3) 借阅记录（reader_no 为真实学号时用 raw，已哈希时用 hashed）
    python scripts/import_school_data.py --borrows 借阅.csv --reader-mode raw
    python scripts/import_school_data.py --borrows 借阅.csv --reader-mode hashed

CSV 列（表头必须一致，大小写不敏感，多余列会被忽略）：
    学生：student_no, name(可选), college, major, class_no, grade
    书目：isbn, title, author, publisher, publish_date, clc_code, call_no,
          pages, price, lib_location, total_copies, available_copies, summary(可选), toc(可选)
    借阅：reader_no, isbn, borrowed_at, due_at(可选), returned_at(可选),
          renew_count(可选), barcode(可选), status(可选)

脱敏：
    reader_no 按 R1 规则做 HMAC-SHA256 后取 16 位（前缀 u_），盐值来自
    --salt / 环境变量 DATA_SALT / backend/.data_salt 文件。
    同一份盐必须长期保存：盐丢了，历史数据的哈希就对不上了。

幂等：
    同一读者 + 同一 ISBN + 同一天借出 视为同一条记录，重复导入会跳过。
"""
import argparse
import csv
import hashlib
import hmac
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import select  # noqa: E402

from app.core.enums import BookSource, BorrowStatus, UserRole, UserStatus  # noqa: E402
from app.core.security import new_id  # noqa: E402
from app.db.base import SessionLocal, init_db  # noqa: E402
from app.db.models import Book, BorrowRecord, User  # noqa: E402

SALT_FILE = BACKEND_DIR / ".data_salt"


def resolve_salt(explicit: str = "") -> str:
    salt = explicit or os.environ.get("DATA_SALT", "")
    if not salt and SALT_FILE.exists():
        salt = SALT_FILE.read_text(encoding="utf-8").strip()
    if not salt:
        raise SystemExit(
            "缺少脱敏盐值。请先执行：\n"
            f"  python -c \"import secrets;open(r'{SALT_FILE}','w').write(secrets.token_hex(16))\"\n"
            "或用 --salt / 环境变量 DATA_SALT 传入。盐值请与数据一起妥善保管，丢失后无法再匹配历史记录。"
        )
    return salt


def hash_reader(raw: str, salt: str) -> str:
    """R1：加盐 HMAC-SHA256 取前 16 位，带 u_ 前缀。"""
    digest = hmac.new(salt.encode(), raw.strip().encode(), hashlib.sha256).hexdigest()
    return f"u_{digest[:16]}"


def norm(row: dict) -> dict:
    return {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        raise SystemExit(f"找不到文件：{path}")
    with path.open(encoding="utf-8-sig", newline="") as handle:  # utf-8-sig 兼容 Excel 导出的 BOM
        return [norm(row) for row in csv.DictReader(handle)]


CST = timezone(timedelta(hours=8))


def parse_date(value: str) -> datetime | None:
    """支持 2026-03-12 / 2026/3/12 / 2026-03-12 09:41:22，按北京时间理解后转存 UTC。"""
    if not value:
        return None
    value = value.replace("/", "-").strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            local = datetime.strptime(value, fmt).replace(tzinfo=CST)
            return local.astimezone(timezone.utc)
        except ValueError:
            continue
    raise ValueError(f"无法识别的日期：{value}")


def to_int(value: str, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def to_float(value: str, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------- 学生


def import_students(db, rows: list[dict], dry_run: bool) -> dict:
    stat = {"total": 0, "created": 0, "updated": 0, "skipped": 0}
    for row in rows:
        student_no = row.get("student_no", "")
        if not student_no:
            stat["skipped"] += 1
            continue
        stat["total"] += 1
        user = db.scalar(select(User).where(User.student_no == student_no))
        payload = {
            "college": row.get("college", ""),
            "major": row.get("major", ""),
            "class_no": row.get("class_no", ""),
            "grade": row.get("grade", ""),
        }
        if user is None:
            stat["created"] += 1
            if not dry_run:
                db.add(
                    User(
                        user_id=new_id("user"),
                        student_no=student_no,
                        name=row.get("name", "") or f"学生{student_no[-4:]}",
                        role=UserRole.STUDENT.value,
                        status=UserStatus.ACTIVE.value,
                        **payload,
                    )
                )
        else:
            changed = [k for k, v in payload.items() if v and getattr(user, k) != v]
            if not changed:
                stat["skipped"] += 1
                continue
            stat["updated"] += 1
            if not dry_run:
                for key in changed:
                    setattr(user, key, payload[key])
    if not dry_run:
        db.flush()
    return stat


# ---------------------------------------------------------------- 书目


def import_books(db, rows: list[dict], dry_run: bool) -> dict:
    stat = {"total": 0, "created": 0, "updated": 0, "skipped": 0}
    for row in rows:
        isbn = row.get("isbn", "")
        title = row.get("title", "")
        if not isbn or not title:
            stat["skipped"] += 1
            continue
        stat["total"] += 1
        fields = {
            "title": title,
            "author": row.get("author", ""),
            "publisher": row.get("publisher", ""),
            "publish_date": row.get("publish_date", "") or None,
            "clc_code": row.get("clc_code", ""),
            "call_no": row.get("call_no", ""),
            "lib_location": row.get("lib_location", ""),
            "pages": to_int(row.get("pages")),
            "price": to_float(row.get("price")),
            "total_copies": to_int(row.get("total_copies")),
            "available_copies": to_int(row.get("available_copies")),
            "summary": row.get("summary", ""),
            "toc": row.get("toc", ""),
        }
        book = db.scalar(select(Book).where(Book.isbn == isbn, Book.is_deleted.is_(False)))
        if book is None:
            stat["created"] += 1
            if not dry_run:
                db.add(Book(book_id=new_id("book"), isbn=isbn, source=BookSource.LIBRARY.value,
                            tags=[], ai_tags=[], **fields))
            continue
        changed = {k: v for k, v in fields.items() if v not in (None, "", 0) and getattr(book, k) != v}
        if not changed:
            stat["skipped"] += 1
            continue
        stat["updated"] += 1
        if not dry_run:
            for key, value in changed.items():
                setattr(book, key, value)
    if not dry_run:
        db.flush()
    return stat


# ---------------------------------------------------------------- 借阅


def import_borrows(db, rows: list[dict], dry_run: bool, salt: str, reader_mode: str) -> dict:
    stat = {"total": 0, "created": 0, "skipped": 0, "unmatched_reader": 0, "unknown_isbn": 0}

    # 预先把库里的学生按哈希建索引，避免逐行查库
    users = db.scalars(select(User).where(User.role != UserRole.VISITOR.value)).all()
    hash_to_user = {hash_reader(u.student_no, salt): u.user_id for u in users}
    books = {b.isbn: b for b in db.scalars(select(Book).where(Book.is_deleted.is_(False))).all()}

    for row in rows:
        reader_no = row.get("reader_no", "")
        isbn = row.get("isbn", "")
        borrowed_at = row.get("borrowed_at", "")
        if not reader_no or not isbn or not borrowed_at:
            stat["skipped"] += 1
            continue
        stat["total"] += 1

        reader_hash = reader_no if reader_mode == "hashed" else hash_reader(reader_no, salt)
        user_id = hash_to_user.get(reader_hash, "")
        if not user_id:
            stat["unmatched_reader"] += 1
        book = books.get(isbn)
        if book is None:
            stat["unknown_isbn"] += 1
            continue

        borrowed = parse_date(borrowed_at)
        due = parse_date(row.get("due_at", ""))
        returned = parse_date(row.get("returned_at", ""))

        exists = db.scalar(
            select(BorrowRecord).where(
                BorrowRecord.reader_hash == reader_hash,
                BorrowRecord.isbn == isbn,
                BorrowRecord.borrowed_at == borrowed,
            )
        )
        if exists is not None:
            stat["skipped"] += 1
            continue

        status = row.get("status", "")
        if status not in {s.value for s in BorrowStatus}:
            status = BorrowStatus.RETURNED.value if returned else BorrowStatus.BORROWING.value

        stat["created"] += 1
        if not dry_run:
            db.add(
                BorrowRecord(
                    borrow_id=new_id("borrow"),
                    user_id=user_id,
                    reader_hash=reader_hash,
                    book_id=book.book_id,
                    isbn=isbn,
                    lib_barcode=row.get("barcode", ""),
                    borrowed_at=borrowed,
                    due_at=due,
                    returned_at=returned,
                    renew_count=to_int(row.get("renew_count")),
                    status=status,
                )
            )
    if not dry_run:
        db.flush()
    return stat


def report(name: str, stat: dict) -> None:
    parts = "，".join(f"{k}={v}" for k, v in stat.items())
    print(f"[import] {name}：{parts}")


def main() -> None:
    parser = argparse.ArgumentParser(description="导入学校脱敏数据（学生 / 书目 / 借阅）")
    parser.add_argument("--students", type=Path, help="学生名单 CSV")
    parser.add_argument("--books", type=Path, help="馆藏书目 CSV")
    parser.add_argument("--borrows", type=Path, help="借阅记录 CSV")
    parser.add_argument("--reader-mode", choices=["raw", "hashed"], default="raw",
                        help="reader_no 是真实学号(raw)还是已哈希(hashed)，默认 raw")
    parser.add_argument("--salt", default="", help="脱敏盐值，不传则读环境变量或 backend/.data_salt")
    parser.add_argument("--dry-run", action="store_true", help="只统计不写入")
    args = parser.parse_args()

    if not any((args.students, args.books, args.borrows)):
        parser.print_help()
        return

    init_db()
    db = SessionLocal()
    try:
        if args.students:
            report("学生", import_students(db, read_csv(args.students), args.dry_run))
        if args.books:
            report("书目", import_books(db, read_csv(args.books), args.dry_run))
        if args.borrows:
            salt = resolve_salt(args.salt)
            if args.reader_mode == "hashed" and not salt:
                pass  # 已哈希时盐只用于匹配，仍需要
            report("借阅", import_borrows(db, read_csv(args.borrows), args.dry_run, salt, args.reader_mode))

        if args.dry_run:
            db.rollback()
            print("[import] dry-run，未写入数据库")
        else:
            db.commit()
            print("[import] 已提交")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
