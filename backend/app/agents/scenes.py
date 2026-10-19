"""四个场景智能体：AI 录书 / AI 匹配 / AI 触达 / AI 伴读。

每个场景都遵循同一个骨架：

    校验入参 → 判断模型是否可用 → 跑 ReAct（模型自己决定调哪些工具）
             → **校验模型输出** → 不合格就降级 → 返回统一结构

其中「校验模型输出」是这一层最不能省的部分。模型会编：
- 荐书场景编出根本不存在的 book_id
- 录书场景把 ISBN 记错一位
- 触达场景把名额写成"不限"

所以凡是能对着数据库核对的，一律核对；对不上的整条剔除，剔除干净了就降级。
"""
from __future__ import annotations

import time
from typing import Any

from sqlalchemy.orm import Session

from app.agents import fallback, runtime
from app.agents.prompts import PROMPTS
from app.agents.tools import (
    SCENE_COMPANION,
    SCENE_INTAKE,
    SCENE_MATCH,
    SCENE_OUTREACH,
    ToolContext,
)
from app.db.models import Activity, Book
from app.services import llm_client


def _result(
    scene: str,
    data: dict[str, Any] | None = None,
    *,
    degraded: bool = False,
    reason: str = "",
    content: str = "",
    run: runtime.AgentResult | None = None,
) -> dict[str, Any]:
    """统一的场景返回结构。API 层直接透出，前端据此渲染轨迹与降级提示。"""
    return {
        "scene": scene,
        "status": "degraded" if degraded else "success",
        "degraded": degraded,
        "degraded_reason": reason,
        "result": data or {},
        "content": content,
        "trace": (run.tool_trace if run else []),
        "steps": (run.steps if run else 0),
        "tokens": (run.tokens if run else 0),
        "model": (run.model if run else ""),
        "elapsed_ms": (run.elapsed_ms if run else 0),
    }


def _should_fallback() -> tuple[bool, str]:
    available, reason = llm_client.is_available()
    return (not available), reason


# ------------------------------------------------------------------ AI 录书


def run_intake(db: Session, user_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    raw_text = str(payload.get("raw_text") or "").strip()
    isbn = str(payload.get("isbn") or "").strip()
    title = str(payload.get("title") or "").strip()
    if not any((raw_text, isbn, title)):
        raise ValueError("raw_text / isbn / title 至少提供一个")

    fallback_flag, fallback_reason = _should_fallback()
    if fallback_flag:
        return _result(SCENE_INTAKE, fallback.intake(db, raw_text, isbn, title), degraded=True, reason=fallback_reason)

    ctx = ToolContext(db=db, user_id=user_id, scene=SCENE_INTAKE)
    message = f"待整理的书目信息：\nISBN：{isbn or '未提供'}\n书名：{title or '未提供'}\n原始文本：{raw_text or '未提供'}"
    run = runtime.run(SCENE_INTAKE, PROMPTS[SCENE_INTAKE], message, ctx, expect_json=True)

    data = run.data or {}
    book = data.get("book") or {}
    if run.degraded or not book.get("title"):
        # 模型没给出可用结构：先用规则版兜底，但要保留「降级」标记
        merged = fallback.intake(db, raw_text, isbn, title)
        if book:
            merged["model_partial"] = book
        return _result(SCENE_INTAKE, merged, degraded=True,
                       reason=run.degraded_reason or "模型输出缺少书名，已转规则整理", run=run)

    # 防编造：ISBN 必须能在输入里找到，或与库里已有书目一致
    picked_isbn = str(book.get("isbn") or "").replace("-", "")
    if picked_isbn and isbn:
        if picked_isbn != isbn.replace("-", ""):
            book["isbn"] = isbn.replace("-", "")
            data.setdefault("review_notes", []).append("模型给出的 ISBN 与输入不一致，已改回输入值")

    duplicate = data.get("duplicate") or {}
    dup_id = str(duplicate.get("book_id") or "")
    if dup_id and db.get(Book, dup_id) is None:
        duplicate["book_id"] = ""
        duplicate["is_duplicate"] = False
        duplicate["reason"] = "模型给出的重复书目标识不存在，已忽略"
    data["duplicate"] = duplicate
    data.setdefault("missing_fields", [])
    data.setdefault("review_notes", [])
    # 录书永远需要人工确认，不给「自动入库」的口子
    data["review_notes"] = list(dict.fromkeys([*data["review_notes"], "本记录需编目老师确认后方可入库"]))
    return _result(SCENE_INTAKE, data, run=run)


# ------------------------------------------------------------------ AI 匹配


def run_match(db: Session, user_id: str, role: str, payload: dict[str, Any]) -> dict[str, Any]:
    query = str(payload.get("query") or payload.get("extra_prompt") or "").strip()
    limit = int(payload.get("limit") or 5)
    limit = max(1, min(10, limit))

    fallback_flag, fallback_reason = _should_fallback()
    # 访客的降级是设计约束（不接真实模型），优先级高于「模型恰好不可用」这个临时状态，
    # 否则线上模型正常时，访客看到的提示会是莫名其妙的一句废话。
    if role == "visitor":
        return _result(SCENE_MATCH, fallback.match(db, "", query, limit),
                       degraded=True, reason="访客账号按设计不接入真实模型，返回规则推荐")
    if fallback_flag:
        return _result(SCENE_MATCH, fallback.match(db, user_id, query, limit),
                       degraded=True, reason=fallback_reason)

    ctx = ToolContext(db=db, user_id=user_id, scene=SCENE_MATCH)
    message = f"读者需求：{query or '未特别说明，请结合我的借阅画像推荐'}。请推荐最多 {limit} 本书。"
    run = runtime.run(SCENE_MATCH, PROMPTS[SCENE_MATCH], message, ctx, expect_json=True)

    items = (run.data or {}).get("items")
    if run.degraded or not isinstance(items, list) or not items:
        merged = fallback.match(db, user_id, query, limit)
        return _result(SCENE_MATCH, merged, degraded=True,
                       reason=run.degraded_reason or "模型未返回可用的推荐列表", run=run)

    # 防编造：逐条核对 book_id，剔掉不存在的；顺带补齐真实书名与库存
    verified: list[dict[str, Any]] = []
    dropped = 0
    for item in items[:limit]:
        book = db.get(Book, str(item.get("book_id") or ""))
        if book is None or book.is_deleted:
            dropped += 1
            continue
        verified.append(
            {
                "book_id": book.book_id,
                "title": book.title,
                "author": book.author,
                "reason": str(item.get("reason") or "")[:80],
                "evidence": item.get("evidence") if isinstance(item.get("evidence"), list) else [],
                "available_copies": book.available_copies,
                "lib_location": book.lib_location,
                "call_no": book.call_no,
            }
        )

    if not verified:
        merged = fallback.match(db, user_id, query, limit)
        return _result(SCENE_MATCH, merged, degraded=True,
                       reason="模型推荐的书目均未通过核对，已转规则匹配", run=run)

    data = {
        "strategy": (run.data or {}).get("strategy") or "profile",
        "items": verified,
        "explanation": (run.data or {}).get("explanation") or "",
        "dropped_unverified": dropped,
    }
    return _result(SCENE_MATCH, data, run=run)


# ------------------------------------------------------------------ AI 触达


def run_outreach(db: Session, user_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    activity_id = str(payload.get("activity_id") or "").strip()
    topic = str(payload.get("topic") or "").strip()
    channel = str(payload.get("channel") or "push").strip()
    if not activity_id and not topic:
        raise ValueError("activity_id 与 topic 至少提供一个")

    fallback_flag, fallback_reason = _should_fallback()
    if fallback_flag:
        return _result(SCENE_OUTREACH, fallback.outreach(db, activity_id, topic, channel),
                       degraded=True, reason=fallback_reason)

    ctx = ToolContext(db=db, user_id=user_id, scene=SCENE_OUTREACH,
                      extra={"activity_id": activity_id, "channel": channel})
    message = (
        f"请为这场活动写推广文案。渠道：{channel}。"
        + (f"活动 ID：{activity_id}。" if activity_id else f"活动主题：{topic}。")
        + "先查活动真实信息，再动笔。"
    )
    run = runtime.run(SCENE_OUTREACH, PROMPTS[SCENE_OUTREACH], message, ctx, expect_json=True)

    data = run.data or {}
    if run.degraded or not data.get("body"):
        merged = fallback.outreach(db, activity_id, topic, channel)
        return _result(SCENE_OUTREACH, merged, degraded=True,
                       reason=run.degraded_reason or "模型未返回可用文案", run=run)

    # 文案里出现的时间/名额要能和活动对上，对不上就提示人工核对（不直接删，因为表述可能是模糊的）
    risk_notes = data.get("risk_notes") if isinstance(data.get("risk_notes"), list) else []
    activity = db.get(Activity, activity_id) if activity_id else None
    if activity is not None:
        if activity.capacity and str(activity.capacity) not in f"{data.get('body','')}{data.get('push_text','')}":
            risk_notes.append(f"文案未提及名额，活动实际名额 {activity.capacity} 人，发布前请确认是否需要补上")
        if activity.level and activity.level != "none":
            risk_notes.append("活动已定级，可在文案中强调证书含金量")
    risk_notes.append("AI 只生成草稿，发布前需主办方确认")

    data["risk_notes"] = list(dict.fromkeys(str(note) for note in risk_notes if note))
    data["activity_id"] = activity.activity_id if activity else ""
    data["channel"] = channel
    # 明确响应「AI 不自动发送」这条设计约束
    data["needs_human_approval"] = True
    return _result(SCENE_OUTREACH, data, run=run)


# ------------------------------------------------------------------ AI 伴读


def run_companion(
    db: Session,
    user_id: str,
    role: str,
    payload: dict[str, Any],
    history: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    question = str(payload.get("question") or payload.get("content") or "").strip()
    book_id = str(payload.get("book_id") or "").strip()
    if not question:
        raise ValueError("question 不能为空")

    fallback_flag, fallback_reason = _should_fallback()
    if fallback_flag:
        return _result(SCENE_COMPANION, fallback.companion(db, user_id, question, book_id, history),
                       degraded=True, reason=fallback_reason)

    ctx = ToolContext(db=db, user_id=user_id, scene=SCENE_COMPANION)
    context_lines = []
    if book_id:
        book = db.get(Book, book_id)
        if book is not None:
            context_lines.append(f"读者正在看《{book.title}》（book_id={book.book_id}）")
    for item in (history or [])[-4:]:
        context_lines.append(f"{item.get('role', 'user')}: {str(item.get('content', ''))[:120]}")
    message = "\n".join([*context_lines, f"读者提问：{question}"])
    run = runtime.run(SCENE_COMPANION, PROMPTS[SCENE_COMPANION], message, ctx, expect_json=True)

    data = run.data or {}
    answer = str(data.get("answer") or "").strip()
    if not answer:
        # 模型直接输出了纯文本（没按 JSON 走），这仍然可用
        if run.content.strip() and not run.degraded:
            data = {"answer": run.content.strip(), "citations": [], "followups": []}
        else:
            merged = fallback.companion(db, user_id, question, book_id, history)
            return _result(SCENE_COMPANION, merged, degraded=True,
                           reason=run.degraded_reason or "模型未返回可用回答", run=run)

    citations = data.get("citations") if isinstance(data.get("citations"), list) else []
    clean: list[dict[str, str]] = []
    for item in citations[:3]:
        ref_id = str(item.get("ref_id") or "")
        title = str(item.get("title") or "")
        # 引用必须是真实存在的书或活动，编造的直接丢掉
        if ref_id and db.get(Book, ref_id) is None and db.get(Activity, ref_id) is None:
            continue
        if not ref_id and not title:
            continue
        clean.append({"title": title, "ref_id": ref_id, "snippet": str(item.get("snippet") or "")[:120]})
    data["citations"] = clean
    data["followups"] = data.get("followups") if isinstance(data.get("followups"), list) else []
    return _result(SCENE_COMPANION, data, run=run)
