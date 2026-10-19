"""初始化演示数据。

用法：
    python scripts/seed.py            # 幂等补齐（已有数据跳过）
    python scripts/seed.py --reset    # 清空业务表后重建（仅演示环境使用）

演示账号（密码统一 123456）：
    admin        系统管理员（全部权限 + 权限分配）
    T2009        普通管理员（图书馆老师，有审批权）
    T2010        普通管理员（审批权已被系统管理员收回）
    2025211987   Alice   学生
    2025211995   万贝    学生 + 额外授予「申办活动」（学生会成员）
    2025211996   Bob     学生（无申办权）
    guest        访客（只读 + AI 推荐降级 Mock）
"""
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select, text  # noqa: E402

from app.core.enums import (  # noqa: E402
    ActivityCategory,
    ActivityLevel,
    ActivityStatus,
    BookSource,
    BorrowStatus,
    CertificateStatus,
    DriftStatus,
    NotificationType,
    SignupStatus,
    SummaryStatus,
    UserRole,
)
from app.core.permissions import Permission  # noqa: E402
from app.core.security import new_id  # noqa: E402
from app.db.base import Base, SessionLocal, engine, init_db  # noqa: E402
from app.db.models import (  # noqa: E402
    Activity,
    ActivitySignup,
    ActivitySummary,
    Book,
    BookFavorite,
    BorrowRecord,
    Certificate,
    DriftRecord,
    Notification,
    ReadingEvent,
    User,
)

CST = timezone(timedelta(hours=8))


def iso(days: int, hour: int = 14) -> datetime:
    base = datetime.now(CST).replace(hour=hour, minute=0, second=0, microsecond=0)
    return (base + timedelta(days=days)).astimezone(timezone.utc)


USERS = [
    dict(student_no="admin", name="系统管理员", role=UserRole.SUPER_ADMIN.value, college="图书馆"),
    dict(student_no="T2009", name="图书馆老师", role=UserRole.ADMIN.value, college="图书馆"),
    dict(student_no="T2010", name="图书馆老师（无审批权）", role=UserRole.ADMIN.value, college="图书馆",
         revoked_permissions=[Permission.ACTIVITY_REVIEW.value]),
    dict(student_no="2025211987", name="Alice", role=UserRole.STUDENT.value, college="信息与通信工程学院"),
    dict(student_no="2025211995", name="万贝", role=UserRole.STUDENT.value, college="计算机学院",
         granted_permissions=[Permission.ACTIVITY_CREATE.value]),
    dict(student_no="2025211996", name="Bob", role=UserRole.STUDENT.value, college="经济管理学院"),
    dict(student_no="guest", name="访客", role=UserRole.VISITOR.value),
]

BOOKS = [
    dict(isbn="9787115428028", title="深度学习", author="Ian Goodfellow 等", publisher="人民邮电出版社",
         publisher_place="北京", publish_date="2017", category="计算机", clc_code="TP181", call_no="TP181/GL2",
         pages=652, price=168.0, binding="平装", lib_location="沙河三层 A 区",
         toc="第 1 章 引言\n第 2 章 线性代数\n第 3 章 概率与信息论\n第 5 章 机器学习基础\n第 6 章 深度前馈网络",
         tags=["人工智能", "机器学习"], borrow_count=86, total_copies=5, available_copies=2),
    dict(isbn="9787115546081", title="Python 编程：从入门到实践", author="Eric Matthes", publisher="人民邮电出版社",
         publisher_place="北京", publish_date="2020", category="计算机", clc_code="TP311", call_no="TP311.56/MT2",
         pages=459, price=89.0, binding="平装", lib_location="沙河三层 A 区",
         toc="第一部分 基础知识\n第二部分 项目实战\n项目 1 外星人入侵\n项目 2 数据可视化\n项目 3 Web 应用程序",
         tags=["Python", "入门"], borrow_count=132, total_copies=8, available_copies=3),
    dict(isbn="9787020002207", title="红楼梦", author="曹雪芹", publisher="人民文学出版社",
         publisher_place="北京", publish_date="1996", category="文学", clc_code="I242.4", call_no="I242.4/CX4",
         pages=1606, price=59.7, binding="精装", lib_location="沙河二层 B 区",
         toc="第一回 甄士隐梦幻识通灵\n第二回 贾夫人仙逝扬州城\n第三回 贾雨村夤缘复旧职",
         tags=["古典文学", "名著"], borrow_count=74, total_copies=10, available_copies=6),
    dict(isbn="9787508647357", title="人类简史", author="尤瓦尔·赫拉利", publisher="中信出版社",
         publisher_place="北京", publish_date="2014", category="历史", clc_code="K02", call_no="K02/HL11",
         pages=440, price=68.0, binding="精装", lib_location="沙河二层 C 区",
         toc="第一部分 认知革命\n第二部分 农业革命\n第三部分 人类的融合统一\n第四部分 科学革命",
         tags=["历史", "文明"], borrow_count=158, total_copies=6, available_copies=1),
    dict(isbn="9787544253994", title="百年孤独", author="加西亚·马尔克斯", publisher="南海出版公司",
         publisher_place="海口", publish_date="2011", category="文学", clc_code="I775.45", call_no="I775.45/MG5",
         pages=360, price=39.5, binding="精装", lib_location="沙河二层 B 区",
         toc="第一章\n第二章\n第三章",
         tags=["拉美文学", "魔幻现实主义"], borrow_count=97, total_copies=4, available_copies=2),
    dict(isbn="9787111636663", title="Vue.js 设计与实现", author="霍春阳", publisher="机械工业出版社",
         publisher_place="北京", publish_date="2022", category="计算机", clc_code="TP393.092", call_no="TP393.092/HC25",
         pages=528, price=119.0, binding="平装", lib_location="沙河三层 A 区",
         toc="第一篇 框架设计概览\n第二篇 响应系统\n第三篇 渲染器\n第四篇 编译器\n第五篇 服务端渲染",
         tags=["前端", "Vue"], borrow_count=45, total_copies=0, available_copies=0),
]

# status / level / organizer_key / offset
ACTIVITIES = [
    dict(title="「书海拾贝」秋季读书分享会", subtitle="与同好共读一本好书", category=ActivityCategory.READING_SHARE.value,
         location="图书馆三层报告厅", capacity=60, status=ActivityStatus.PUBLISHED.value, level=ActivityLevel.SCHOOL.value,
         signup_count=42, need_certificate=True, organizer="T2009", start_offset=5, signup_end_offset=3),
    dict(title="AI 时代的深度阅读主题讲座", subtitle="当大模型遇见图书馆", category=ActivityCategory.LECTURE.value,
         location="学术交流中心 201", capacity=120, status=ActivityStatus.SIGNUP_CLOSED.value, level=ActivityLevel.SCHOOL.value,
         signup_count=118, need_certificate=True, organizer="T2009", start_offset=1, signup_end_offset=-1),
    dict(title="21 天阅读打卡挑战（第一期）", subtitle="每天 30 分钟，养成阅读习惯", category=ActivityCategory.READING_CHALLENGE.value,
         location="线上打卡 + 小程序", capacity=0, status=ActivityStatus.FINISHED.value, level=ActivityLevel.SCHOOL.value,
         signup_count=3, checkin_count=2, need_certificate=True, organizer="T2009", start_offset=-20, signup_end_offset=-25),
    dict(title="闲置图书漂流集市（预告）", subtitle="让好书流动起来", category=ActivityCategory.BOOK_DRIFT.value,
         location="图书馆一层大厅", capacity=200, status=ActivityStatus.DRAFT.value, level=ActivityLevel.NONE.value,
         signup_count=0, need_certificate=False, organizer="T2009", start_offset=12, signup_end_offset=8),
    dict(title="「书页间的光」校园摄影展", subtitle="用镜头记录阅读现场", category=ActivityCategory.EXHIBITION.value,
         location="图书馆二层展廊", capacity=80, status=ActivityStatus.PENDING_REVIEW.value, level=ActivityLevel.NONE.value,
         signup_count=0, need_certificate=True, organizer="2025211995", start_offset=18, signup_end_offset=14),
    dict(title="旧书交换市集（第二期）", subtitle="换一本没读过的书", category=ActivityCategory.BOOK_DRIFT.value,
         location="图书馆一层大厅", capacity=100, status=ActivityStatus.REJECTED.value, level=ActivityLevel.NONE.value,
         signup_count=0, need_certificate=False, organizer="2025211995", start_offset=25, signup_end_offset=21),
    dict(title="「共读一本书」院级分享会", subtitle="院系联合阅读活动", category=ActivityCategory.READING_SHARE.value,
         location="沙河校区学生活动中心", capacity=50, status=ActivityStatus.FINISHED.value, level=ActivityLevel.COLLEGE.value,
         signup_count=2, checkin_count=2, need_certificate=True, organizer="T2009", start_offset=-45, signup_end_offset=-50),
]

SUMMARY_TEXT = (
    "21 天阅读打卡第一期共吸引 236 名同学参与，累计打卡 3,842 次，人均阅读时长 42 分钟/天。\n\n"
    "本期共读《人类简史》《百年孤独》两本书，线下分享会上有 12 位同学做了主题发言。"
    "从打卡数据看，晚上 21:00—23:00 是阅读高峰，建议下一期把线上答疑安排在这个时段。\n\n"
    "感谢每一位坚持到最后的同学，第二期将于下月启动。"
)


def reset_tables() -> None:
    Base.metadata.drop_all(bind=engine)
    # 连 alembic_version 一起清掉，再按新库流程建表并打版本，保证与迁移链一致
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE IF EXISTS alembic_version"))
    init_db()
    print("[seed] 已清空并重建所有表（--reset）")


def _ensure_user(db, data: dict) -> User:
    row = db.scalar(select(User).where(User.student_no == data["student_no"]))
    granted = data.get("granted_permissions", [])
    revoked = data.get("revoked_permissions", [])
    payload = {k: v for k, v in data.items() if k not in ("granted_permissions", "revoked_permissions")}
    if row is None:
        row = User(**payload, granted_permissions=granted, revoked_permissions=revoked)
        db.add(row)
        db.flush()
        print(f"[seed] 新增用户 {data['student_no']} {data['name']}（{data['role']}）")
    else:
        row.role = data["role"]
        row.name = data["name"]
        row.college = data.get("college", row.college)
        row.granted_permissions = granted
        row.revoked_permissions = revoked
    return row


def _ensure_activity(db, data: dict, users: dict[str, User]) -> Activity:
    row = db.scalar(select(Activity).where(Activity.title == data["title"], Activity.is_deleted.is_(False)))
    organizer = users[data["organizer"]]
    if row is None:
        row = Activity(
            activity_id=new_id("activity"),
            title=data["title"],
            subtitle=data["subtitle"],
            category=data["category"],
            location=data["location"],
            capacity=data["capacity"],
            status=data["status"],
            level=data["level"],
            signup_count=data.get("signup_count", 0),
            checkin_count=data.get("checkin_count", 0),
            need_certificate=data["need_certificate"],
            certificate_template_id="tpl_default" if data["need_certificate"] else "",
            organizer_id=organizer.user_id,
            organizer_name=organizer.name,
            start_at=iso(data["start_offset"]),
            end_at=iso(data["start_offset"], hour=17),
            signup_start_at=iso(data["signup_end_offset"] - 10),
            signup_end_at=iso(data["signup_end_offset"]),
            published_at=iso(-2) if data["status"] in (
                ActivityStatus.PUBLISHED.value, ActivityStatus.SIGNUP_CLOSED.value,
                ActivityStatus.ONGOING.value, ActivityStatus.FINISHED.value,
            ) else None,
            submitted_at=iso(-3) if data["status"] not in (
                ActivityStatus.DRAFT.value, ActivityStatus.PUBLISHED.value
            ) else None,
        )
        if data["status"] in (ActivityStatus.PUBLISHED.value, ActivityStatus.SIGNUP_CLOSED.value,
                              ActivityStatus.ONGOING.value, ActivityStatus.FINISHED.value):
            reviewer = users["T2009"]
            row.reviewed_by = reviewer.user_id
            row.reviewed_by_name = reviewer.name
            row.reviewed_at = iso(-3)
            row.review_comment = "主题与图书馆阅读推广方向一致，同意立项"
        if data["status"] == ActivityStatus.REJECTED.value:
            row.review_comment = "时间与馆内其他活动冲突，请调整后重新提交"
        db.add(row)
        db.flush()
        print(f"[seed] 新增活动 {data['title']}（{data['status']}）")
    return row


def _seed_ai_data(db, users: dict[str, User]) -> None:
    """借阅记录 / 收藏 / 阅读行为：第三块「智能体」开发时的数据地基。

    只给两个学生账号造少量样本，用于验证表结构与后续推荐链路；
    真实数据进来后这些演示记录可整体清掉。
    """
    if db.scalar(select(BorrowRecord).limit(1)) is not None:
        return

    books = {b.isbn: b for b in db.scalars(select(Book)).all()}
    plans = {
        "2025211987": [  # Alice：偏技术 + 历史
            ("9787115546081", -120, 30, 28, 1),
            ("9787115428028", -80, 30, 26, 0),
            ("9787508647357", -45, 30, 21, 0),
            ("9787111636663", -12, 30, None, 0),  # 在借
        ],
        "2025211995": [  # 万贝：偏文学
            ("9787020002207", -150, 30, 27, 2),
            ("9787544253994", -90, 30, 25, 0),
            ("9787508647357", -30, 30, None, 1),  # 在借
        ],
    }
    for student_no, items in plans.items():
        user = users.get(student_no)
        if user is None:
            continue
        for isbn, borrow_offset, due_offset, return_offset, renew in items:
            book = books.get(isbn)
            if book is None:
                continue
            db.add(
                BorrowRecord(
                    borrow_id=new_id("borrow"),
                    user_id=user.user_id,
                    book_id=book.book_id,
                    isbn=isbn,
                    lib_barcode=f"B2023-{uuid.uuid4().hex[:6].upper()}",
                    borrowed_at=iso(borrow_offset, 10),
                    due_at=iso(borrow_offset + due_offset, 10),
                    returned_at=iso(return_offset, 16) if return_offset is not None else None,
                    renew_count=renew,
                    status=BorrowStatus.RETURNED.value if return_offset is not None else BorrowStatus.BORROWING.value,
                )
            )

    favorites = [
        ("2025211987", "9787111636663", "想系统学一下响应式原理", 5),
        ("2025211987", "9787508647357", "", 4),
        ("2025211995", "9787020002207", "重读第三遍", 5),
    ]
    for student_no, isbn, note, rating in favorites:
        user, book = users.get(student_no), books.get(isbn)
        if user is None or book is None:
            continue
        db.add(
            BookFavorite(
                favorite_id=new_id("favorite"),
                user_id=user.user_id,
                book_id=book.book_id,
                note=note,
                rating=rating,
            )
        )

    events = [
        ("2025211987", "search", "", "", "推荐系统 协同过滤", -9),
        ("2025211987", "view_book", "9787115428028", "", "", -8),
        ("2025211987", "ai_recommend", "", "", "想找几本机器学习入门书", -8),
        ("2025211987", "favorite", "9787111636663", "", "", -6),
        ("2025211987", "view_activity", "", "act", "", -5),
        ("2025211995", "search", "", "", "好看的短篇小说", -7),
        ("2025211995", "view_book", "9787544253994", "", "", -6),
        ("2025211995", "ai_chat", "9787020002207", "", "红楼梦前五回人物关系", -4),
        ("2025211995", "summary_view", "", "summary", "", -3),
    ]
    for student_no, event_type, isbn, ref_type, keyword, day in events:
        user = users.get(student_no)
        if user is None:
            continue
        book = books.get(isbn) if isbn else None
        db.add(
            ReadingEvent(
                event_id=new_id("event"),
                user_id=user.user_id,
                event_type=event_type,
                book_id=book.book_id if book else "",
                ref_id="",
                keyword=keyword,
                score=0,
                duration_sec=0,
                scene="pc",
                created_at=iso(day, 20),
            )
        )
    print(f"[seed] 已生成借阅 / 收藏 / 行为样本（借阅 {sum(len(v) for v in plans.values())} 条，"
          f"收藏 {len(favorites)} 条，行为 {len(events)} 条）")


def main() -> None:
    if "--reset" in sys.argv:
        reset_tables()
    else:
        init_db()

    db = SessionLocal()
    try:
        users = {u["student_no"]: _ensure_user(db, u) for u in USERS}
        db.flush()

        for idx, b in enumerate(BOOKS):
            exists = db.scalar(select(Book).where(Book.isbn == b["isbn"], Book.is_deleted.is_(False)))
            if exists is None:
                db.add(Book(**b, source=BookSource.DRIFT.value if idx == 5 else BookSource.LIBRARY.value, ai_tags=[]))
        db.flush()

        activities = {data["title"]: _ensure_activity(db, data, users) for data in ACTIVITIES}

        # 已结束活动的报名名单 + 证书
        finished = activities["21 天阅读打卡挑战（第一期）"]
        finished_college = activities["「共读一本书」院级分享会"]
        alice = users["2025211987"]
        wanbei = users["2025211995"]
        for activity, extra_user in ((finished, alice), (finished, wanbei), (finished_college, alice), (finished_college, wanbei)):
            exists = db.scalar(
                select(ActivitySignup).where(
                    ActivitySignup.activity_id == activity.activity_id,
                    ActivitySignup.user_id == extra_user.user_id,
                )
            )
            if exists is None:
                db.add(
                    ActivitySignup(
                        signup_id=new_id("signup"),
                        activity_id=activity.activity_id,
                        user_id=extra_user.user_id,
                        status=SignupStatus.APPROVED.value,
                        signed_up_at=activity.signup_start_at or iso(-30),
                        checked_in_at=activity.start_at,
                    )
                )
        db.flush()

        year = datetime.now(CST).year
        for activity, student in ((finished, alice), (finished, wanbei), (finished_college, alice)):
            exists = db.scalar(
                select(Certificate).where(
                    Certificate.activity_id == activity.activity_id,
                    Certificate.user_id == student.user_id,
                )
            )
            if exists is None:
                verify_code = uuid.uuid4().hex[:8].upper()
                level_code = "S" if activity.level == ActivityLevel.SCHOOL.value else "C"
                cert = Certificate(
                    certificate_id=new_id("certificate"),
                    serial_no=f"ZYYC-{year}-{level_code}-{verify_code}",
                    verify_code=verify_code,
                    user_id=student.user_id,
                    student_name=student.name,
                    student_no=student.student_no,
                    college=student.college,
                    activity_id=activity.activity_id,
                    activity_title=activity.title,
                    activity_level=activity.level,
                    certificate_name="荣誉证书",
                    seal_name="北京邮电大学图书馆",
                    issued_by=users["T2009"].user_id,
                    issued_by_name=users["T2009"].name,
                    issued_at=iso(-18),
                    status=CertificateStatus.ISSUED.value,
                )
                db.add(cert)
                db.flush()
                signup = db.scalar(
                    select(ActivitySignup).where(
                        ActivitySignup.activity_id == activity.activity_id,
                        ActivitySignup.user_id == student.user_id,
                    )
                )
                if signup is not None:
                    signup.certificate_no = cert.serial_no
        db.flush()

        # 活动总结 + 推送（访客也能看到）
        exists = db.scalar(select(ActivitySummary).where(ActivitySummary.activity_id == finished.activity_id))
        if exists is None:
            summary = ActivitySummary(
                summary_id=new_id("summary"),
                activity_id=finished.activity_id,
                activity_title=finished.title,
                title="21 天，我们一起读完了两本书",
                content=SUMMARY_TEXT,
                images=[],
                author_id=users["T2009"].user_id,
                author_name=users["T2009"].name,
                status=SummaryStatus.PUBLISHED.value,
                published_at=iso(-17),
                view_count=126,
            )
            db.add(summary)
            db.flush()
            db.add(
                Notification(
                    notification_id=new_id("notification"),
                    type=NotificationType.ACTIVITY_SUMMARY.value,
                    title=f"活动回顾：{summary.title}",
                    content=SUMMARY_TEXT[:200],
                    ref_type="activity_summary",
                    ref_id=summary.summary_id,
                    target_roles=["student", "visitor", "admin", "super_admin"],
                    created_by=users["T2009"].user_id,
                    created_by_name=users["T2009"].name,
                )
            )

        # 漂流池
        drift_book = db.scalar(select(Book).where(Book.isbn == "9787111636663"))
        if drift_book is not None and db.scalar(select(DriftRecord).where(DriftRecord.book_id == drift_book.book_id)) is None:
            db.add(
                DriftRecord(
                    drift_id=new_id("drift"),
                    book_id=drift_book.book_id,
                    current_holder_id=users["T2009"].user_id,
                    drift_status=DriftStatus.IDLE.value,
                    drift_location="图书馆一层大厅",
                )
            )

        _seed_ai_data(db, users)

        db.commit()
        print("[seed] 完成 ✅")
        print("[seed] 演示账号 / 密码 123456：admin(系统管理员) T2009(管理员,可审批) T2010(管理员,无审批权) "
              "2025211987(学生) 2025211995(学生,可申办活动) guest(访客)")
    finally:
        db.close()


if __name__ == "__main__":
    main()
