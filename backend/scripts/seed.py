"""初始化演示数据：python scripts/seed.py

演示账号（密码统一 123456）：
- admin      系统管理员   role=admin
- T2009      施怀鹃       role=librarian
- 2025211987 Alice        role=student
"""
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select  # noqa: E402

from app.core.enums import ActivityCategory, ActivityStatus, BookSource, DriftStatus, UserRole  # noqa: E402
from app.db.base import SessionLocal, init_db  # noqa: E402
from app.db.models import Activity, Book, User  # noqa: E402

CST = timezone(timedelta(hours=8))


def iso(days: int, hour: int = 14) -> datetime:
    base = datetime.now(CST).replace(hour=hour, minute=0, second=0, microsecond=0)
    return base + timedelta(days=days)


USERS = [
    dict(student_no="admin", name="系统管理员", role=UserRole.ADMIN.value, college="图书馆"),
    dict(student_no="T2009", name="施怀鹃", role=UserRole.LIBRARIAN.value, college="图书馆", email="shi2009@bupt.edu.cn"),
    dict(student_no="2025211987", name="Alice", role=UserRole.STUDENT.value),
]

BOOKS = [
    dict(isbn="9787115428028", title="深度学习", author="Ian Goodfellow 等", publisher="人民邮电出版社", category="TP181", tags=["人工智能", "机器学习"], borrow_count=86, total_copies=5, available_copies=2),
    dict(isbn="9787115546081", title="Python 编程：从入门到实践", author="Eric Matthes", publisher="人民邮电出版社", category="TP311", tags=["Python", "入门"], borrow_count=132, total_copies=8, available_copies=3),
    dict(isbn="9787020002207", title="红楼梦", author="曹雪芹", publisher="人民文学出版社", category="I242", tags=["古典文学", "名著"], borrow_count=74, total_copies=10, available_copies=6),
    dict(isbn="9787508647357", title="人类简史", author="尤瓦尔·赫拉利", publisher="中信出版社", category="K02", tags=["历史", "文明"], borrow_count=158, total_copies=6, available_copies=1),
    dict(isbn="9787544253994", title="百年孤独", author="加西亚·马尔克斯", publisher="南海出版公司", category="I775", tags=["拉美文学", "魔幻现实主义"], borrow_count=97, total_copies=4, available_copies=2),
    dict(isbn="9787111636663", title="Vue.js 设计与实现", author="霍春阳", publisher="机械工业出版社", category="TP393", tags=["前端", "Vue"], borrow_count=45, total_copies=3, available_copies=3),
]

ACTIVITIES = [
    dict(title="「书海拾贝」秋季读书分享会", subtitle="与同好共读一本好书", category=ActivityCategory.READING_SHARE.value, location="图书馆三层报告厅", capacity=60, status=ActivityStatus.PUBLISHED.value, signup_count=42, checkin_count=0, need_certificate=True, start_offset=5, signup_offset_end=3),
    dict(title="AI 时代的深度阅读主题讲座", subtitle="当大模型遇见图书馆", category=ActivityCategory.LECTURE.value, location="学术交流中心 201", capacity=120, status=ActivityStatus.SIGNUP_CLOSED.value, signup_count=118, checkin_count=0, need_certificate=True, start_offset=1, signup_offset_end=-1),
    dict(title="21 天阅读打卡挑战（第一期）", subtitle="每天 30 分钟，养成阅读习惯", category=ActivityCategory.READING_CHALLENGE.value, location="线上打卡 + 小程序", capacity=0, status=ActivityStatus.FINISHED.value, signup_count=236, checkin_count=189, need_certificate=False, start_offset=-20, signup_offset_end=-25),
    dict(title="闲置图书漂流集市（预告）", subtitle="让好书流动起来", category=ActivityCategory.BOOK_DRIFT.value, location="图书馆一层大厅", capacity=200, status=ActivityStatus.DRAFT.value, signup_count=0, checkin_count=0, need_certificate=False, start_offset=12, signup_offset_end=8),
]


def main() -> None:
    init_db()
    db = SessionLocal()
    try:
        if db.scalar(select(User).limit(1)) is None:
            for u in USERS:
                db.add(User(**u))
            print(f"[seed] 用户 {len(USERS)} 条")
        else:
            print("[seed] 用户已存在，跳过")

        if db.scalar(select(Book).limit(1)) is None:
            for idx, b in enumerate(BOOKS):
                source = BookSource.DRIFT.value if idx == 5 else BookSource.LIBRARY.value
                db.add(Book(**b, source=source, drift_status=DriftStatus.IDLE.value if source == BookSource.DRIFT.value else DriftStatus.CLOSED.value))
            print(f"[seed] 图书 {len(BOOKS)} 条")
        else:
            print("[seed] 图书已存在，跳过")

        organizer = db.scalar(select(User).where(User.name == "施怀鹃"))
        if db.scalar(select(Activity).limit(1)) is None:
            for a in ACTIVITIES:
                start_off = a.pop("start_offset")
                signup_end_off = a.pop("signup_offset_end")
                db.add(
                    Activity(
                        **a,
                        organizer_id=organizer.user_id if organizer else "usr_seed",
                        organizer_name=organizer.name if organizer else "",
                        start_at=iso(start_off),
                        end_at=iso(start_off, hour=17),
                        signup_start_at=iso(signup_end_off - 10),
                        signup_end_at=iso(signup_end_off),
                        published_at=iso(-2) if a["status"] != ActivityStatus.DRAFT.value else None,
                    )
                )
            print(f"[seed] 活动 {len(ACTIVITIES)} 条")
        else:
            print("[seed] 活动已存在，跳过")

        db.commit()
        print("[seed] 完成 ✅")
    finally:
        db.close()


if __name__ == "__main__":
    main()
