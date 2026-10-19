"""智能体统一入口。

和第一轮 `/ai/chat` 的区别：这里不是「一问一答」，而是「派一件事，智能体自己去查」。
调用方只描述目标（帮我挑书 / 把这场活动写成推送），过程中调了哪些工具、
查了什么数据，都在返回的 trace 里。

四个场景的权限口径：
    intake     book:manage      编目老师 / 管理员
    match      ai:recommend     学生可用；访客可用但强制降级
    outreach   activity:create  有申办权的人（AI 只出草稿，发布权仍在人）
    companion  ai:chat          学生及以上，访客不可用
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agents import scenes, tools
from app.agents.prompts import SCENE_LABELS
from app.api.v1.deps import page_query
from app.core.config import settings
from app.core.enums import ConversationScene, MessageRole
from app.core.permissions import Permission
from app.core.response import CODE_NOT_FOUND, CODE_PARAM_ERROR, CODE_SERVER_ERROR, BizError, ok, page_result
from app.core.security import CurrentUser, get_current_user, new_id
from app.db.base import get_db
from app.db.models import AIConversation, AgentRun
from app.schemas.agent import AgentRunRequest
from app.schemas.common import PageQuery
from app.services import llm_client

router = APIRouter(prefix="/agents", tags=["智能体"])

SCENE_PERMISSIONS = {
    "intake": Permission.BOOK_MANAGE,
    "match": Permission.AI_RECOMMEND,
    "outreach": Permission.ACTIVITY_CREATE,
    "companion": Permission.AI_CHAT,
}

# 两个场景产出的是「草稿」而非写库动作：录书只给待确认的书目记录，触达只给待发布的文案，
# 因此学生也可以用。访客仍不开放，避免匿名账号消耗额度。
SCENE_ROLES = {
    "intake": {"student", "admin", "super_admin"},
    "outreach": {"student", "admin", "super_admin"},
}


def scene_allowed(scene: str, current: CurrentUser) -> bool:
    """场景可用性 = 角色白名单 或 持有对应权限（管理员/被额外授权者）。"""
    if scene in SCENE_ROLES and current.role in SCENE_ROLES[scene]:
        return True
    required = SCENE_PERMISSIONS.get(scene)
    return bool(required and current.can(required.value))


def _require_scene(scene: str) -> str:
    if scene not in SCENE_PERMISSIONS:
        raise BizError(CODE_PARAM_ERROR, f"未知场景 {scene}，可选：{'、'.join(SCENE_PERMISSIONS)}")
    return scene


def _input_summary(scene: str, payload: AgentRunRequest) -> str:
    if scene == "intake":
        raw = payload.title or payload.isbn or payload.raw_text
        return f"录入：{raw[:120]}"
    if scene == "match":
        return f"找书：{payload.query[:120] or '（按画像推荐）'}"
    if scene == "outreach":
        return f"文案：{payload.topic[:80] or payload.activity_id}（{payload.channel}）"
    return f"提问：{(payload.question or payload.query)[:120]}"


def _output_summary(scene: str, data: dict) -> str:
    if scene == "intake":
        book = data.get("book") or {}
        if data.get("duplicate", {}).get("is_duplicate"):
            return f"判定重复：{book.get('title', '')}"
        return f"整理出《{book.get('title', '')}》，待确认字段 {len(data.get('missing_fields') or [])} 个"
    if scene == "match":
        items = data.get("items") or []
        return f"推荐 {len(items)} 本：" + "、".join(str(item.get("title", ""))[:12] for item in items[:3])
    if scene == "outreach":
        return f"文案草稿：{str(data.get('title', ''))[:60]}"
    return f"回答 {len(str(data.get('answer', '')))} 字，引用 {len(data.get('citations') or [])} 条"


def _record_run(db: Session, current: CurrentUser, scene: str, payload: AgentRunRequest, result: dict) -> AgentRun:
    run = AgentRun(
        scene=scene,
        user_id=current.user_id,
        user_name=current.name,
        input_summary=_input_summary(scene, payload)[:255],
        status=result.get("status", "success"),
        degraded_reason=str(result.get("degraded_reason") or "")[:255],
        steps=int(result.get("steps") or 0),
        tool_calls=result.get("trace") or [],
        tokens=int(result.get("tokens") or 0),
        model=str(result.get("model") or "")[:64],
        elapsed_ms=int(result.get("elapsed_ms") or 0),
        output_summary=_output_summary(scene, result.get("result") or {})[:255],
    )
    db.add(run)
    return run


def _attach_conversation(
    db: Session, current: CurrentUser, payload: AgentRunRequest, result: dict
) -> str:
    """伴读场景把问答写进会话，方便 PC 端和小程序共用同一份历史。"""
    data = result.get("result") or {}
    answer = str(data.get("answer") or "")
    question = (payload.question or payload.query).strip()
    if not answer or not question:
        return ""

    conv = db.get(AIConversation, payload.conversation_id) if payload.conversation_id else None
    if conv is not None and (conv.user_id != current.user_id or conv.is_deleted):
        conv = None

    now = datetime.now(timezone.utc).isoformat()
    if conv is None:
        conv = AIConversation(
            user_id=current.user_id,
            scene=ConversationScene.QA.value,
            title=question[:20],
            book_id=payload.book_id or None,
            model=result.get("model") or "degraded",
            messages=[],
            message_count=0,
            prompt_version=settings.PROMPT_VERSION,
        )
        db.add(conv)
        db.flush()

    messages = list(conv.messages or [])
    messages.append({"message_id": new_id("message"), "role": MessageRole.USER.value, "content": question, "tokens": 0, "created_at": now})
    messages.append(
        {
            "message_id": new_id("message"),
            "role": MessageRole.ASSISTANT.value,
            "content": answer,
            "tokens": int(result.get("tokens") or 0),
            "created_at": now,
        }
    )
    conv.messages = messages
    conv.message_count = len(messages)
    return conv.conversation_id


@router.get("/health", summary="模型与工具链可用性（前端据此决定是否显示降级提示）")
def health():
    available, reason = llm_client.is_available()
    return ok(
        {
            "available": available,
            "reason": reason,
            "provider": settings.LLM_PROVIDER,
            "model": settings.LLM_MODEL,
            "tools_enabled": settings.AGENT_TOOLS_ENABLED,
            "max_steps": settings.AGENT_MAX_STEPS,
            "token_budget": settings.AGENT_TOKEN_BUDGET,
        }
    )


@router.get("/tools", summary="四个场景与各自可调用的工具")
def list_tools(current: CurrentUser = Depends(get_current_user)):
    data = []
    for scene, (label, description) in SCENE_LABELS.items():
        data.append(
            {
                "scene": scene,
                "label": label,
                "description": description,
                "permission": SCENE_PERMISSIONS[scene].value,
                "allowed": scene_allowed(scene, current),
                "tools": tools.describe_for(scene),
            }
        )
    return ok({"scenes": data})


def _run_scene(scene: str, payload: AgentRunRequest, current: CurrentUser, db: Session) -> dict:
    if scene == "intake":
        return scenes.run_intake(db, current.user_id, payload.model_dump(), current.role)
    if scene == "match":
        return scenes.run_match(db, current.user_id, current.role, payload.model_dump())
    if scene == "outreach":
        can_manage_all = current.role in {"admin", "super_admin"} or current.can(
            Permission.ACTIVITY_MANAGE_ALL.value
        )
        return scenes.run_outreach(db, current.user_id, payload.model_dump(), can_manage_all=can_manage_all)

    # companion：带上一轮对话再交给智能体
    history: list[dict] = []
    if payload.conversation_id:
        conv = db.get(AIConversation, payload.conversation_id)
        if conv is not None and conv.user_id == current.user_id and not conv.is_deleted:
            history = list(conv.messages or [])
    return scenes.run_companion(db, current.user_id, current.role, payload.model_dump(), history)


@router.post("/{scene}/run", summary="执行一次智能体任务（intake / match / outreach / companion）")
def run_scene(
    scene: str,
    payload: AgentRunRequest,
    current: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_scene(scene)
    if not scene_allowed(scene, current):
        raise BizError(1003, "当前账号没有使用该智能体场景的权限", http_status=403)

    if scene == "match" and not (payload.query or payload.book_id):
        # 允许空 query：等于「按我的画像推荐」，这是最常见的用法
        pass

    try:
        result = _run_scene(scene, payload, current, db)
    except ValueError as exc:
        db.rollback()
        raise BizError(CODE_PARAM_ERROR, str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 - 智能体失败不应 500 裸奔
        db.rollback()
        raise BizError(CODE_SERVER_ERROR, f"智能体执行失败：{type(exc).__name__}", http_status=503) from exc

    conversation_id = ""
    if scene == "companion":
        conversation_id = _attach_conversation(db, current, payload, result)

    run = _record_run(db, current, scene, payload, result)
    db.commit()
    db.refresh(run)

    return ok(
        {
            **result,
            "run_id": run.run_id,
            "conversation_id": conversation_id,
        }
    )


@router.get("/dataset", summary="数据来源统计：当前有多少是 AI 模拟数据、多少是真实数据")
def dataset(current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    """学校脱敏数据到位前后，用来判断系统里跑的是什么。

    前端在推荐页顶部据此显示「当前为模拟数据」的提示，
    避免演示时被误认为真实馆藏行为。
    """
    from app.db.models import Book, BookFavorite, BorrowRecord, ReadingEvent, User

    def count_by_source(model) -> dict[str, int]:
        rows = db.execute(select(model.data_source, func.count()).group_by(model.data_source)).all()
        return {(source or "real"): int(total) for source, total in rows}

    users = count_by_source(User)
    books = count_by_source(Book)
    borrows = count_by_source(BorrowRecord)
    events = count_by_source(ReadingEvent)
    favorites = count_by_source(BookFavorite)

    simulated = sum(
        [
            users.get("simulated", 0),
            books.get("simulated", 0),
            borrows.get("simulated", 0),
            events.get("simulated", 0),
            favorites.get("simulated", 0),
        ]
    )
    return ok(
        {
            "users": users,
            "books": books,
            "borrows": borrows,
            "events": events,
            "favorites": favorites,
            "has_simulated": simulated > 0,
            "simulated_total": simulated,
            "hint": "当前包含 AI 模拟数据；真实脱敏数据到位后执行 scripts/simulate_data.py --purge --purge-books 即可替换"
            if simulated
            else "当前数据全部来自真实导入或人工录入",
        }
    )


@router.get("/runs", summary="智能体运行记录（管理员看全部，其他人只看自己）")
def list_runs(
    pq: PageQuery = Depends(page_query),
    scene: str = Query(default=""),
    status: str = Query(default=""),
    current: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    stmt = select(AgentRun).where(AgentRun.is_deleted.is_(False))
    if not current.can(Permission.SYSTEM_PERMISSION):
        stmt = stmt.where(AgentRun.user_id == current.user_id)
    if scene:
        stmt = stmt.where(AgentRun.scene == scene)
    if status:
        stmt = stmt.where(AgentRun.status == status)

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(AgentRun.created_at.desc()).offset((pq.page - 1) * pq.page_size).limit(pq.page_size)
    ).all()
    items = [
        {
            "run_id": row.run_id,
            "scene": row.scene,
            "user_name": row.user_name,
            "input_summary": row.input_summary,
            "output_summary": row.output_summary,
            "status": row.status,
            "degraded_reason": row.degraded_reason,
            "steps": row.steps,
            "tokens": row.tokens,
            "model": row.model,
            "elapsed_ms": row.elapsed_ms,
            "tool_calls": row.tool_calls or [],
            "created_at": row.created_at.isoformat() if row.created_at else "",
        }
        for row in rows
    ]
    return ok(page_result(items, pq.page, pq.page_size, total))


@router.get("/runs/{run_id}", summary="单次运行的完整轨迹")
def get_run(run_id: str, current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(AgentRun, run_id)
    if row is None or row.is_deleted:
        raise BizError(CODE_NOT_FOUND, "运行记录不存在")
    if row.user_id != current.user_id and not current.can(Permission.SYSTEM_PERMISSION):
        raise BizError(1003, "无权查看他人运行记录", http_status=403)
    return ok(
        {
            "run_id": row.run_id,
            "scene": row.scene,
            "user_name": row.user_name,
            "input_summary": row.input_summary,
            "output_summary": row.output_summary,
            "status": row.status,
            "degraded_reason": row.degraded_reason,
            "steps": row.steps,
            "tokens": row.tokens,
            "model": row.model,
            "elapsed_ms": row.elapsed_ms,
            "tool_calls": row.tool_calls or [],
            "created_at": row.created_at.isoformat() if row.created_at else "",
        }
    )
