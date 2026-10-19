"""智能体可调用的工具集。

设计约束（很重要，别破坏）：
1. **只读**。除录书场景由前端保存草稿外，智能体不直接改业务数据。写操作一律留给人工确认。
2. **不返回整条 ORM 记录**。每个工具只挑模型决策需要的字段，把 summary/toc 这类长文本
   截断，否则一次工具结果就能吃掉整个上下文预算。
3. **不返回他人隐私**。`user_profile` / `user_history` 只能读当前登录用户，且只返回聚合结果。
4. **失败不抛异常**。返回 {"ok": false, "error": "..."} 让模型自己纠错或换个工具，
   一次工具参数写错不该让整次对话挂掉。

每个工具声明 `scenes`，运行时只把该场景允许的工具发给模型，
避免伴读场景突然去查活动报名名单这类越界行为。
"""
from __future__ import annotations

import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.enums import ACTIVITY_PUBLIC_STATUSES
from app.db.models import Activity, Book, BookFavorite, BorrowRecord, ReadingEvent, User

# 场景常量（与 agents 包保持一致，避免循环导入）
SCENE_INTAKE = "intake"        # AI 录书
SCENE_MATCH = "match"          # AI 匹配
SCENE_OUTREACH = "outreach"    # AI 触达
SCENE_COMPANION = "companion"  # AI 伴读


@dataclass
class ToolContext:
    """一次运行内的上下文。db 是全流程复用的会话，不要在这里 commit。"""

    db: Session
    user_id: str = ""
    role: str = "visitor"
    scene: str = ""
    extra: dict[str, Any] = field(default_factory=dict)
    # 工具调用轨迹，运行结束后写进 agent_runs.tool_calls
    trace: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]
    scenes: set[str]
    handler: Callable[[ToolContext, dict[str, Any]], dict[str, Any]]


REGISTRY: dict[str, ToolSpec] = {}


def tool(name: str, description: str, parameters: dict[str, Any], scenes: set[str]):
    def decorator(func: Callable[[ToolContext, dict[str, Any]], dict[str, Any]]):
        REGISTRY[name] = ToolSpec(name, description, parameters, scenes, func)
        return func

    return decorator


# ------------------------------------------------------------------ 参数工具


def _clamp(value: Any, low: int, high: int, default: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(low, min(high, number))


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _cut(text: str, limit: int = 160) -> str:
    text = (text or "").strip().replace("\n", " ")
    return text if len(text) <= limit else text[:limit] + "…"


def _book_brief(book: Book) -> dict[str, Any]:
    return {
        "book_id": book.book_id,
        "title": book.title,
        "author": book.author,
        "category": book.category,
        "clc_code": book.clc_code or book.category,
        "tags": (book.tags or [])[:5],
        "available_copies": book.available_copies,
        "total_copies": book.total_copies,
        "borrow_count": book.borrow_count,
    }


def _fmt_dt(value: datetime | None) -> str:
    return value.strftime("%Y-%m-%d %H:%M") if value else ""


# ------------------------------------------------------------------ 书目类


@tool(
    name="search_books",
    description="按关键词（书名/作者/主题词）检索馆藏图书。不知道具体书名、想找某一类书时用这个。",
    parameters={
        "type": "object",
        "properties": {
            "keyword": {"type": "string", "description": "检索词，如「机器学习」「余华」「心理学」"},
            "category": {"type": "string", "description": "中图法分类号前缀，如 TP 表示计算机类，可留空"},
            "available_only": {"type": "boolean", "description": "是否只看当前可借的书，默认 false"},
            "limit": {"type": "integer", "description": "返回条数，1-10，默认 5"},
        },
        "required": ["keyword"],
    },
    scenes={SCENE_MATCH, SCENE_COMPANION, SCENE_INTAKE, SCENE_OUTREACH},
)
def search_books(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    keyword = _text(args.get("keyword"))
    category = _text(args.get("category"))
    available_only = bool(args.get("available_only"))
    limit = _clamp(args.get("limit"), 1, 10, 5)
    if not keyword and not category:
        return {"ok": False, "error": "keyword 与 category 至少填一个"}

    stmt = select(Book).where(Book.is_deleted.is_(False))
    if keyword:
        like = f"%{keyword}%"
        stmt = stmt.where(or_(Book.title.like(like), Book.author.like(like), Book.summary.like(like)))
    if category:
        stmt = stmt.where(or_(Book.clc_code.like(f"{category}%"), Book.category.like(f"{category}%")))
    if available_only:
        stmt = stmt.where(Book.available_copies > 0)

    rows = ctx.db.scalars(stmt.order_by(Book.borrow_count.desc()).limit(limit)).all()
    return {"ok": True, "count": len(rows), "books": [_book_brief(book) for book in rows]}


@tool(
    name="get_book",
    description="按书名或 ISBN 取单本书的完整馆藏信息（含索书号、馆藏地、可借数量、简介）。",
    parameters={
        "type": "object",
        "properties": {"title_or_isbn": {"type": "string", "description": "书名（可模糊）或 13 位 ISBN"}},
        "required": ["title_or_isbn"],
    },
    scenes={SCENE_MATCH, SCENE_COMPANION, SCENE_INTAKE, SCENE_OUTREACH},
)
def get_book(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    key = _text(args.get("title_or_isbn"))
    if not key:
        return {"ok": False, "error": "title_or_isbn 不能为空"}

    stmt = select(Book).where(Book.is_deleted.is_(False))
    stmt = stmt.where(Book.isbn == key) if key.isdigit() and len(key) in (10, 13) else stmt.where(Book.title.like(f"%{key}%"))
    book = ctx.db.scalars(stmt.limit(1)).first()
    if book is None:
        return {"ok": False, "error": f"馆藏中没有找到「{key}」"}

    return {
        "ok": True,
        "book": {
            **_book_brief(book),
            "isbn": book.isbn,
            "publisher": book.publisher,
            "publish_date": book.publish_date,
            "call_no": book.call_no,
            "lib_location": book.lib_location,
            "pages": book.pages,
            "summary": _cut(book.summary, 200),
            "ai_summary": _cut(book.ai_summary, 200),
            "toc": _cut(book.toc, 200),
        },
    }


@tool(
    name="book_stats",
    description="查某本书近半年的借阅、收藏、浏览热度，用于判断这本书是否值得推荐。",
    parameters={
        "type": "object",
        "properties": {"book_id": {"type": "string", "description": "书目主键，来自 search_books 结果"}},
        "required": ["book_id"],
    },
    scenes={SCENE_MATCH, SCENE_INTAKE, SCENE_OUTREACH},
)
def book_stats(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    book_id = _text(args.get("book_id"))
    book = ctx.db.get(Book, book_id) if book_id else None
    if book is None or book.is_deleted:
        return {"ok": False, "error": "书目不存在"}

    since = datetime.now(timezone.utc) - timedelta(days=180)
    borrows = ctx.db.scalar(
        select(func.count()).select_from(BorrowRecord).where(BorrowRecord.book_id == book_id, BorrowRecord.borrowed_at >= since)
    ) or 0
    favorites = ctx.db.scalar(select(func.count()).select_from(BookFavorite).where(BookFavorite.book_id == book_id)) or 0
    views = ctx.db.scalar(
        select(func.count()).select_from(ReadingEvent).where(ReadingEvent.book_id == book_id, ReadingEvent.created_at >= since)
    ) or 0
    return {
        "ok": True,
        "book_id": book_id,
        "title": book.title,
        "total_borrow_count": book.borrow_count,
        "borrow_180d": borrows,
        "favorite_count": favorites,
        "view_180d": views,
        "available_copies": book.available_copies,
    }


@tool(
    name="similar_books",
    description="找与某本书同分类或同标签的其他书，用于「看完这本还想看什么」。",
    parameters={
        "type": "object",
        "properties": {
            "book_id": {"type": "string", "description": "源书目主键"},
            "limit": {"type": "integer", "description": "返回条数 1-8，默认 4"},
        },
        "required": ["book_id"],
    },
    scenes={SCENE_MATCH, SCENE_COMPANION},
)
def similar_books(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    book_id = _text(args.get("book_id"))
    limit = _clamp(args.get("limit"), 1, 8, 4)
    book = ctx.db.get(Book, book_id) if book_id else None
    if book is None or book.is_deleted:
        return {"ok": False, "error": "书目不存在"}

    conditions = [Book.book_id != book_id, Book.is_deleted.is_(False)]
    match_terms = []
    if book.clc_code:
        match_terms.append(Book.clc_code.like(f"{book.clc_code[:3]}%"))
    if book.category:
        match_terms.append(Book.category == book.category)
    if book.author:
        match_terms.append(Book.author == book.author)
    if match_terms:
        conditions.append(or_(*match_terms))

    rows = ctx.db.scalars(
        select(Book).where(*conditions).order_by(Book.borrow_count.desc()).limit(limit)
    ).all()
    return {"ok": True, "source": book.title, "count": len(rows), "books": [_book_brief(item) for item in rows]}


@tool(
    name="hot_books",
    description="近 N 天借阅量最高的书，用于热门榜、冷启动推荐。",
    parameters={
        "type": "object",
        "properties": {
            "days": {"type": "integer", "description": "统计窗口，7-180 天，默认 30"},
            "limit": {"type": "integer", "description": "返回条数 1-10，默认 5"},
        },
        "required": [],
    },
    scenes={SCENE_MATCH, SCENE_OUTREACH, SCENE_COMPANION},
)
def hot_books(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    days = _clamp(args.get("days"), 7, 180, 30)
    limit = _clamp(args.get("limit"), 1, 10, 5)
    since = datetime.now(timezone.utc) - timedelta(days=days)

    rows = ctx.db.execute(
        select(Book, func.count(BorrowRecord.borrow_id).label("recent"))
        .join(BorrowRecord, BorrowRecord.book_id == Book.book_id, isouter=True)
        .where(Book.is_deleted.is_(False))
        .group_by(Book.book_id)
        .order_by(func.count(BorrowRecord.borrow_id).desc(), Book.borrow_count.desc())
        .limit(limit)
    ).all()
    return {
        "ok": True,
        "window_days": days,
        "books": [{**_book_brief(book), "borrow_in_window": int(recent or 0)} for book, recent in rows],
    }


# ------------------------------------------------------------------ 读者类


@tool(
    name="user_profile",
    description="取当前读者自己的阅读画像（偏好分类、高频标签、借阅与收藏统计）。做个性化推荐前先调它。",
    parameters={"type": "object", "properties": {}, "required": []},
    scenes={SCENE_MATCH, SCENE_COMPANION, SCENE_OUTREACH},
)
def user_profile(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    if not ctx.user_id:
        return {"ok": False, "error": "访客没有阅读画像，请改用 hot_books 或 search_books"}

    user = ctx.db.get(User, ctx.user_id)
    if user is None:
        return {"ok": False, "error": "用户不存在"}

    since = datetime.now(timezone.utc) - timedelta(days=180)
    borrow_rows = ctx.db.execute(
        select(Book.category, Book.clc_code)
        .join(BorrowRecord, BorrowRecord.book_id == Book.book_id)
        .where(BorrowRecord.user_id == ctx.user_id)
    ).all()
    favorite_rows = ctx.db.scalars(select(BookFavorite).where(BookFavorite.user_id == ctx.user_id)).all()
    favorite_books = [ctx.db.get(Book, fav.book_id) for fav in favorite_rows]
    favorite_books = [book for book in favorite_books if book is not None]
    recent_events = ctx.db.scalar(
        select(func.count()).select_from(ReadingEvent).where(ReadingEvent.user_id == ctx.user_id, ReadingEvent.created_at >= since)
    ) or 0

    categories = Counter([row[0] for row in borrow_rows if row[0]])
    clc_codes = Counter([row[1] for row in borrow_rows if row[1]])
    tag_counter: Counter = Counter()
    for book in favorite_books:
        for tag in (book.tags or [])[:3]:
            tag_counter[tag] += 1

    return {
        "ok": True,
        "college": user.college,
        "major": user.major,
        "grade": user.grade,
        "borrow_total": len(borrow_rows),
        "favorite_total": len(favorite_books),
        "active_events_180d": recent_events,
        "top_categories": [{"category": name, "count": count} for name, count in categories.most_common(3)],
        "top_clc_codes": [{"clc_code": code, "count": count} for code, count in clc_codes.most_common(3)],
        "top_tags": [{"tag": tag, "count": count} for tag, count in tag_counter.most_common(5)],
    }


@tool(
    name="user_history",
    description="取当前读者最近借过的书，用于「接着上次读」「别推已经看过的」。",
    parameters={
        "type": "object",
        "properties": {"limit": {"type": "integer", "description": "返回条数 1-10，默认 5"}},
        "required": [],
    },
    scenes={SCENE_MATCH, SCENE_COMPANION},
)
def user_history(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    if not ctx.user_id:
        return {"ok": False, "error": "访客没有借阅历史"}
    limit = _clamp(args.get("limit"), 1, 10, 5)

    rows = ctx.db.execute(
        select(BorrowRecord, Book)
        .join(Book, Book.book_id == BorrowRecord.book_id, isouter=True)
        .where(BorrowRecord.user_id == ctx.user_id)
        .order_by(BorrowRecord.borrowed_at.desc())
        .limit(limit)
    ).all()
    items = [
        {
            "title": book.title if book else record.isbn,
            "book_id": record.book_id,
            "category": book.category if book else "",
            "borrowed_at": _fmt_dt(record.borrowed_at),
            "returned": record.returned_at is not None,
        }
        for record, book in rows
    ]
    return {"ok": True, "count": len(items), "items": items}


# ------------------------------------------------------------------ 活动类


@tool(
    name="list_activities",
    description="查当前已发布/进行中的阅读活动，可按关键词或状态过滤。",
    parameters={
        "type": "object",
        "properties": {
            "keyword": {"type": "string", "description": "活动主题关键词，可留空"},
            "status": {"type": "string", "description": "published / signup_closed / ongoing / finished，可留空"},
            "limit": {"type": "integer", "description": "返回条数 1-10，默认 5"},
        },
        "required": [],
    },
    scenes={SCENE_OUTREACH, SCENE_COMPANION, SCENE_MATCH},
)
def list_activities(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    keyword = _text(args.get("keyword"))
    status = _text(args.get("status"))
    limit = _clamp(args.get("limit"), 1, 10, 5)

    public_statuses = [item.value for item in ACTIVITY_PUBLIC_STATUSES]
    stmt = select(Activity).where(Activity.is_deleted.is_(False), Activity.status.in_(public_statuses))
    if keyword:
        stmt = stmt.where(or_(Activity.title.like(f"%{keyword}%"), Activity.summary.like(f"%{keyword}%")))
    if status in public_statuses:
        stmt = stmt.where(Activity.status == status)

    rows = ctx.db.scalars(stmt.order_by(Activity.start_at.desc()).limit(limit)).all()
    return {
        "ok": True,
        "count": len(rows),
        "activities": [
            {
                "activity_id": item.activity_id,
                "title": item.title,
                "category": item.category,
                "level": item.level,
                "status": item.status,
                "start_at": _fmt_dt(item.start_at),
                "location": item.location,
                "signup_count": item.signup_count,
                "capacity": item.capacity,
            }
            for item in rows
        ],
    }


@tool(
    name="activity_detail",
    description="查单个活动的详情与报名情况，写推文前先调它拿准确信息。",
    parameters={
        "type": "object",
        "properties": {"activity_id": {"type": "string", "description": "活动主键"}},
        "required": ["activity_id"],
    },
    scenes={SCENE_OUTREACH, SCENE_COMPANION},
)
def activity_detail(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    activity_id = _text(args.get("activity_id"))
    item = ctx.db.get(Activity, activity_id) if activity_id else None
    if item is None or item.is_deleted:
        return {"ok": False, "error": "活动不存在"}
    return {
        "ok": True,
        "activity": {
            "activity_id": item.activity_id,
            "title": item.title,
            "subtitle": item.subtitle,
            "category": item.category,
            "level": item.level,
            "status": item.status,
            "location": item.location,
            "start_at": _fmt_dt(item.start_at),
            "end_at": _fmt_dt(item.end_at),
            "signup_start_at": _fmt_dt(item.signup_start_at),
            "signup_end_at": _fmt_dt(item.signup_end_at),
            "capacity": item.capacity,
            "signup_count": item.signup_count,
            "need_certificate": item.need_certificate,
            "summary": _cut(item.summary, 200),
            "content": _cut(item.content, 300),
        },
    }


@tool(
    name="activity_audience",
    description="统计活动目标人群特征（学院分布、年级分布），写推送文案时用来确定语气与卖点。",
    parameters={
        "type": "object",
        "properties": {"activity_id": {"type": "string", "description": "活动主键"}},
        "required": ["activity_id"],
    },
    scenes={SCENE_OUTREACH},
)
def activity_audience(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    activity_id = _text(args.get("activity_id"))
    item = ctx.db.get(Activity, activity_id) if activity_id else None
    if item is None or item.is_deleted:
        return {"ok": False, "error": "活动不存在"}

    from app.db.models import ActivitySignup

    rows = ctx.db.execute(
        select(User.college, User.grade)
        .join(ActivitySignup, ActivitySignup.user_id == User.user_id)
        .where(ActivitySignup.activity_id == activity_id)
    ).all()
    colleges = Counter([row[0] for row in rows if row[0]])
    grades = Counter([row[1] for row in rows if row[1]])
    return {
        "ok": True,
        "signup_total": len(rows),
        "colleges": [{"college": name, "count": count} for name, count in colleges.most_common(3)],
        "grades": [{"grade": name, "count": count} for name, count in grades.most_common(3)],
        "capacity_left": max(0, item.capacity - item.signup_count),
    }


# ------------------------------------------------------------------ 对外接口


def schemas_for(scene: str) -> list[dict[str, Any]]:
    """生成 OpenAI tools 参数。只暴露该场景声明的工具。"""
    return [
        {"type": "function", "function": {"name": spec.name, "description": spec.description, "parameters": spec.parameters}}
        for spec in REGISTRY.values()
        if scene in spec.scenes
    ]


def describe_for(scene: str) -> list[dict[str, str]]:
    """给前端展示「这个智能体能查什么」，纯文本。"""
    return [
        {"name": spec.name, "description": spec.description}
        for spec in REGISTRY.values()
        if scene in spec.scenes
    ]


def dispatch(name: str, arguments: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    """执行工具。任何异常都转成 ok=false，并把轨迹写进 ctx.trace。"""
    spec = REGISTRY.get(name)
    started = time.perf_counter()
    if spec is None:
        result = {"ok": False, "error": f"未知工具 {name}"}
    elif ctx.scene and ctx.scene not in spec.scenes:
        result = {"ok": False, "error": f"当前场景不允许调用 {name}"}
    else:
        try:
            result = spec.handler(ctx, arguments or {})
            if not isinstance(result, dict):
                result = {"ok": False, "error": "工具返回值格式异常"}
        except Exception as exc:  # noqa: BLE001 - 工具内部错误不应中断整个智能体
            ctx.db.rollback()
            result = {"ok": False, "error": f"工具执行失败：{type(exc).__name__}: {exc}"}

    ctx.trace.append(
        {
            "tool": name,
            "arguments": arguments or {},
            "ok": bool(result.get("ok")),
            "summary": _summarize(name, result),
            "elapsed_ms": int((time.perf_counter() - started) * 1000),
        }
    )
    return result


def _summarize(name: str, result: dict[str, Any]) -> str:
    """给运行轨迹生成一句人话，前端时间线直接展示。"""
    if not result.get("ok"):
        return str(result.get("error") or "调用失败")
    if "books" in result:
        books = result["books"]
        return f"找到 {len(books)} 本：" + "、".join(book.get("title", "") for book in books[:3])
    if "book" in result:
        return f"《{result['book'].get('title', '')}》"
    if "activities" in result:
        items = result["activities"]
        return f"活动 {len(items)} 个：" + "、".join(item.get("title", "") for item in items[:3])
    if "activity" in result:
        return f"活动《{result['activity'].get('title', '')}》"
    if "items" in result:
        return f"历史 {len(result['items'])} 条"
    if name == "user_profile":
        return f"画像：主要偏好 {'、'.join(item['category'] for item in result.get('top_categories', [])) or '暂无'}"
    if name == "book_stats":
        return f"借阅 {result.get('total_borrow_count')} 次，可借 {result.get('available_copies')} 册"
    return "已完成"
