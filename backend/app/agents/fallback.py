"""规则降级：没有模型、模型报错、访客受限时，四个场景仍然要能跑。

这不是「假装智能体在工作」。降级结果会明确标注 degraded=true 和原因，
前端顶部会出现提示条。目的是让演示、开发和离线环境不至于因为一个 key 就全盘停摆。

降级实现只做确定性计算：关键词匹配、分类统计、模板套用。
"""
from __future__ import annotations

import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.enums import ACTIVITY_PUBLIC_STATUSES
from app.db.models import Activity, Book, BookFavorite, BorrowRecord, User

ISBN_RE = re.compile(r"(?:97[89][-\s]?)?\d{9}[\dXx]")
CJK_RE = re.compile(r"[\u4e00-\u9fa5]{2,}")
FIELD_RE = {
    "title": re.compile(r"(?:书名|题名)[：:]\s*(.+)"),
    "author": re.compile(r"(?:作者|著者)[：:]\s*(.+)"),
    "publisher": re.compile(r"出版社[：:]\s*(.+)"),
    "isbn": re.compile(r"ISBN[：:\s]*([\d\-Xx]{10,20})", re.IGNORECASE),
}

# 常见主题词 → 中图法大类，用于降级时补分类号
TOPIC_TO_CLC = {
    "计算机": "TP", "编程": "TP", "算法": "TP", "人工智能": "TP", "机器学习": "TP",
    "数据": "TP", "网络": "TP", "软件": "TP",
    "文学": "I", "小说": "I", "散文": "I", "诗歌": "I",
    "历史": "K", "哲学": "B", "心理": "B", "经济": "F", "管理": "F",
    "数学": "O", "物理": "O", "化学": "O", "生物": "Q", "艺术": "J",
}


def _cut(text: str, limit: int) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else text[:limit]


def _parse_isbn(text: str) -> str:
    match = ISBN_RE.search(text or "")
    if not match:
        return ""
    raw = re.sub(r"[-\s]", "", match.group(0))
    return raw if len(raw) in (10, 13) else ""


def _extract_fields(text: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for key, pattern in FIELD_RE.items():
        match = pattern.search(text or "")
        if match:
            value = match.group(1).strip()
            if key == "isbn":
                value = re.sub(r"[-\s]", "", value)
            fields[key] = _cut(value, 64)
    return fields


def _keywords(text: str) -> list[str]:
    """粗糙但够用的关键词抽取：连续中文片段 + 英文单词。"""
    tokens = CJK_RE.findall(text or "")
    tokens += re.findall(r"[A-Za-z]{2,}", text or "")
    # 长片段再切成 2~4 字的小段，提高命中率
    expanded: list[str] = []
    for token in tokens:
        if len(token) <= 4:
            expanded.append(token)
        else:
            expanded.extend(token[i : i + 3] for i in range(0, len(token) - 2, 2))
    return list(dict.fromkeys([item for item in expanded if len(item) >= 2]))[:12]


# ------------------------------------------------------------------ AI 录书


def intake(db: Session, raw_text: str, isbn: str = "", title: str = "") -> dict[str, Any]:
    text = f"{raw_text or ''} {title or ''}".strip()
    parsed = _extract_fields(text)
    picked_isbn = re.sub(r"[-\s]", "", isbn or parsed.get("isbn") or _parse_isbn(text))
    picked_title = (title or parsed.get("title") or "").strip()

    existing = None
    if picked_isbn:
        existing = db.scalars(select(Book).where(Book.isbn == picked_isbn).limit(1)).first()
    if existing is None and picked_title:
        existing = db.scalars(select(Book).where(Book.title.like(f"%{picked_title}%")).limit(1)).first()

    if existing is not None:
        return {
            "duplicate": {"is_duplicate": True, "book_id": existing.book_id, "reason": "馆藏中已存在同一本书"},
            "book": {"title": existing.title, "isbn": existing.isbn},
            "confidence": 0.2,
            "missing_fields": [],
            "review_notes": ["该书已入库，无需重复录入"],
        }

    tags: list[str] = []
    for topic, clc in TOPIC_TO_CLC.items():
        if topic in text:
            tags.append(topic)
            if "clc_code" not in parsed:
                parsed["clc_code"] = clc
    book = {
        "title": picked_title or parsed.get("title", ""),
        "subtitle": "",
        "author": parsed.get("author", ""),
        "translator": "",
        "publisher": parsed.get("publisher", ""),
        "publisher_place": "",
        "publish_date": "",
        "isbn": picked_isbn,
        "clc_code": parsed.get("clc_code", ""),
        "call_no": "",
        "pages": 0,
        "price": 0,
        "binding": "",
        "category": parsed.get("clc_code", ""),
        "lib_location": "",
        "summary": _cut(text, 120),
        "toc": "",
        "tags": tags[:5],
    }
    missing = [key for key, value in book.items() if not value and key not in ("subtitle", "translator", "publisher_place", "binding", "toc")]
    return {
        "duplicate": {"is_duplicate": False, "book_id": "", "reason": "未能匹配到已有馆藏"},
        "book": book,
        "confidence": 0.3,
        "missing_fields": missing,
        "review_notes": ["已按规则抽取字段，分类号与馆藏地需图书馆老师补充"],
    }


# ------------------------------------------------------------------ AI 匹配


def match(db: Session, user_id: str, query: str, limit: int) -> dict[str, Any]:
    limit = max(1, min(10, limit))
    keywords = _keywords(query)
    borrowed_ids: set[str] = set()
    major_cls: Counter = Counter()  # 中图法大类，如 T / I / K
    sub_cls: Counter = Counter()    # 前两位，如 TP / I2 / K2

    if user_id:
        borrowed_ids = set(
            db.scalars(select(BorrowRecord.book_id).where(BorrowRecord.user_id == user_id)).all()
        )
        rows = db.execute(
            select(Book.clc_code, Book.category)
            .join(BorrowRecord, BorrowRecord.book_id == Book.book_id)
            .where(BorrowRecord.user_id == user_id)
        ).all()
        for clc, category in rows:
            code = (clc or category or "").strip()
            if len(code) >= 2:
                major_cls[code[0]] += 1
                sub_cls[code[:2]] += 1

    candidates = db.scalars(select(Book).where(Book.is_deleted.is_(False)).limit(300)).all()
    # 热度做归一化基准，避免「借得多的书永远赢」压过兴趣匹配
    max_borrow = max([book.borrow_count for book in candidates] or [1]) or 1

    scored: list[tuple[float, Book, list[str]]] = []
    for book in candidates:
        if book.book_id in borrowed_ids:
            continue
        score = 0.0
        evidence: list[str] = []
        code = (book.clc_code or book.category or "").strip()

        haystack = f"{book.title}{book.author}{book.category}{book.summary}{''.join(book.tags or [])}"
        hit = [word for word in keywords if word in haystack]
        if hit:
            score += len(hit) * 3
            evidence.append(f"主题命中「{'、'.join(hit[:2])}」")
        # 兴趣匹配按「占比」加权，而不是「命中就加分」：
        # 借过 6 本 I2 和借过 1 本 TP 都叫"命中"，但偏好强度差 6 倍，不能给同样的分。
        total_history = sum(sub_cls.values()) or 1
        sub_ratio = sub_cls.get(code[:2], 0) / total_history if code[:2] else 0
        major_ratio = major_cls.get(code[:1], 0) / total_history if code[:1] else 0
        if sub_ratio:
            score += sub_ratio * 10
            evidence.append(f"你借过 {sub_cls[code[:2]]} 本 {code[:2]} 类")
        elif major_ratio:
            score += major_ratio * 5
            evidence.append(f"与你常读的 {code[:1]} 类同属一类")
        score += min(book.borrow_count / max_borrow, 1.0) * 1.5
        if book.borrow_count:
            evidence.append(f"累计借出 {book.borrow_count} 次")
        if book.available_copies > 0:
            score += 1.0
            evidence.append(f"当前可借 {book.available_copies} 册")
        scored.append((score, book, evidence))

    scored.sort(key=lambda item: item[0], reverse=True)
    strategy = "keyword" if keywords else ("profile" if major_cls else "hot")
    items = []
    basis_hit = 0
    for _, book, evidence in scored[:limit]:
        matched = any(("你借过" in note or "同属一类" in note or "主题命中" in note) for note in evidence)
        if matched:
            basis_hit += 1
        label = "、".join(book.tags[:2]) or book.category or "综合"
        if matched:
            reason = f"与你常读的方向一致，{label}，馆内可借 {book.available_copies} 册。"
        else:
            reason = f"馆内热门，{label}方向，馆内可借 {book.available_copies} 册。"
        items.append(
            {
                "book_id": book.book_id,
                "title": book.title,
                "author": book.author,
                "reason": reason,
                "evidence": evidence,
                "available_copies": book.available_copies,
                "lib_location": book.lib_location,
            }
        )

    if not major_cls:
        explanation = "暂无借阅画像，先按馆内热度推荐。"
    elif basis_hit == 0:
        explanation = "你常读的分类暂无可借新书，以下为同馆热门。"
    elif basis_hit < len(items):
        explanation = f"{len(items)} 本中 {basis_hit} 本命中你的借阅偏好，其余为热门。"
    else:
        explanation = f"{basis_hit} 本均命中你的借阅偏好（同分类或关键词）。"
    return {"strategy": strategy, "items": items, "explanation": explanation}


# ------------------------------------------------------------------ AI 触达


def outreach(db: Session, activity_id: str, topic: str, channel: str) -> dict[str, Any]:
    activity = db.get(Activity, activity_id) if activity_id else None
    if activity is None and topic:
        activity = db.scalars(
            select(Activity)
            .where(Activity.is_deleted.is_(False), Activity.title.like(f"%{topic}%"))
            .order_by(Activity.start_at.desc())
            .limit(1)
        ).first()

    if activity is None:
        recent = db.scalars(
            select(Activity)
            .where(Activity.is_deleted.is_(False), Activity.status.in_([item.value for item in ACTIVITY_PUBLIC_STATUSES]))
            .order_by(Activity.start_at.desc())
            .limit(1)
        ).first()
        activity = recent

    if activity is None:
        return {
            "title": topic or "读书活动",
            "body": "暂无可引用的活动信息，请先创建活动再生成文案。",
            "push_text": "",
            "tags": [],
            "audience_hint": "",
            "risk_notes": ["未找到活动，文案未生成"],
        }

    when = activity.start_at.strftime("%m 月 %d 日 %H:%M") if activity.start_at else "时间待定"
    left = max(0, activity.capacity - activity.signup_count)
    body = (
        f"{activity.summary or activity.title}，{when} 在{activity.location or '校内'}举行。\n\n"
        f"现场会围绕主题做分享与共读，名额 {activity.capacity} 人"
        + ("，参与者可获得电子证书。" if activity.need_certificate else "。")
        + f"\n\n目前在「智阅校园」活动页开放报名，剩余 {left} 个名额。"
    )
    return {
        "title": _cut(activity.title, 20),
        "body": body,
        "push_text": _cut(f"{activity.title}｜{when}｜{activity.location or '校内'}，剩余 {left} 个名额", 60),
        "tags": ["阅读推广", activity.category],
        "audience_hint": "全校学生",
        "risk_notes": ["文案由模板生成，时间地点请与活动详情再核对一次"],
    }


# ------------------------------------------------------------------ AI 伴读


def companion(db: Session, user_id: str, question: str, book_id: str = "", history: list | None = None) -> dict[str, Any]:
    text = question or ""
    citations: list[dict[str, str]] = []

    book = db.get(Book, book_id) if book_id else None
    if book is None:
        for word in _keywords(text):
            book = db.scalars(select(Book).where(Book.title.like(f"%{word}%")).limit(1)).first()
            if book is not None:
                break

    if book is not None:
        location = book.lib_location or "馆藏地待确认"
        stock = f"可借 {book.available_copies} 册" if book.available_copies else "当前已全部借出"
        answer = (
            f"《{book.title}》在馆里，{location}，索书号 {book.call_no or '待确认'}，{stock}。\n\n"
            f"{_cut(book.summary, 90) or '这本书的简介暂时没有录入。'}\n\n"
            "（当前为降级回答，未启用模型，只能回到书目数据本身。）"
        )
        citations.append({"title": book.title, "ref_id": book.book_id, "snippet": f"{location} · {stock}"})
        followups = ["这本书适合什么基础读？", "有没有同类的书推荐？"]
    elif any(word in text for word in ("活动", "讲座", "报名")):
        rows = db.scalars(
            select(Activity)
            .where(Activity.is_deleted.is_(False), Activity.status.in_([item.value for item in ACTIVITY_PUBLIC_STATUSES]))
            .order_by(Activity.start_at.desc())
            .limit(3)
        ).all()
        if rows:
            lines = [f"· {item.title}（{item.start_at.strftime('%m-%d') if item.start_at else '时间待定'}，{item.location or '地点待定'}）" for item in rows]
            answer = "近期在办的活动有：\n" + "\n".join(lines) + "\n\n在活动页可以直接报名。"
            citations = [{"title": item.title, "ref_id": item.activity_id, "snippet": item.location} for item in rows[:2]]
        else:
            answer = "目前没有正在报名的活动，有新活动会在这里出现。"
        followups = ["有适合新生的活动吗？", "活动能拿证书吗？"]
    elif any(word in text for word in ("借", "续借", "还书", "逾期")):
        answer = (
            "借阅天数、续借次数、逾期处理这些规则每个学校不一样，我不敢给你一个具体数字，"
            "以免误导。图书馆官网或者借阅台能查到准确规定。\n\n"
            "如果你是想知道自己借的书什么时候到期，可以在「我的借阅」里看，或者告诉我书名，我帮你查馆藏位置。"
        )
        followups = ["帮我找一本讲时间管理的书", "最近有什么读书活动？"]
    else:
        answer = (
            "现在没接上模型，我只能回答跟馆藏和活动直接相关的问题，"
            "比如「《人类简史》在哪个馆藏区」「最近有什么读书活动」。\n\n"
            "等模型恢复后，聊书、聊观点、做阅读计划都可以。"
        )
        followups = ["《人类简史》在哪个馆藏区？", "推荐几本心理学入门"]
    return {"answer": answer, "citations": citations, "followups": followups}
