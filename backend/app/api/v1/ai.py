"""AI 会话：多轮对话（含 SSE 流式）+ 会话管理 + 文案生成。"""
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.v1.deps import page_query
from app.core.enums import ConversationScene, ConversationStatus, MessageRole
from app.core.response import CODE_NOT_FOUND, BizError, ok, page_result
from app.core.security import CurrentUser, get_current_user, new_id
from app.db.base import get_db
from app.db.models import AIConversation, Book
from app.schemas.ai import ChatRequest, ChatResponse, ConversationBrief, ConversationOut, CopywritingRequest, ChatMessage
from app.schemas.common import PageQuery
from app.services import llm_service

router = APIRouter(prefix="/ai", tags=["AI 能力"])


def _get_conversation(db: Session, conversation_id: str, user_id: str) -> AIConversation:
    row = db.get(AIConversation, conversation_id)
    if row is None or row.is_deleted:
        raise BizError(CODE_NOT_FOUND, "会话不存在")
    if row.user_id != user_id:
        raise BizError(1003, "无权访问他人会话", http_status=403)
    return row


@router.post("/chat", summary="多轮对话（stream=true 时返回 SSE 流）")
def chat(payload: ChatRequest, current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    book = db.get(Book, payload.book_id) if payload.book_id else None

    if payload.conversation_id:
        conv = _get_conversation(db, payload.conversation_id, current.user_id)
    else:
        conv = AIConversation(
            user_id=current.user_id,
            scene=payload.scene,
            title=payload.message[:20],
            book_id=payload.book_id,
            book_title=book.title if book else "",
            model=payload.model or llm_service.settings.LLM_MODEL,
            messages=[],
            message_count=0,
            prompt_version=payload.prompt_version or llm_service.settings.PROMPT_VERSION,
        )
        db.add(conv)
        db.flush()

    user_msg = {
        "message_id": new_id("message"),
        "role": MessageRole.USER.value,
        "content": payload.message,
        "tokens": 0,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    answer, tokens = llm_service.chat_reply(conv.scene, payload.message, book)
    assistant_msg = {
        "message_id": new_id("message"),
        "role": MessageRole.ASSISTANT.value,
        "content": answer,
        "tokens": tokens,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    conv.messages = [*(conv.messages or []), user_msg, assistant_msg]
    conv.message_count = len(conv.messages)
    conv.status = ConversationStatus.ACTIVE.value
    db.commit()
    db.refresh(conv)

    if payload.stream:
        return StreamingResponse(
            _sse_stream(conv.conversation_id, assistant_msg["message_id"], answer),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return ok(
        ChatResponse(
            conversation_id=conv.conversation_id,
            message=ChatMessage(**assistant_msg),
            model=conv.model,
            prompt_version=conv.prompt_version,
        ).model_dump()
    )


def _sse_stream(conversation_id: str, message_id: str, text: str, chunk_size: int = 12):
    """SSE 帧格式与规范 5.3 节一致，双端共用同一解析逻辑。"""
    for i in range(0, len(text), chunk_size):
        frame = {"delta": text[i : i + chunk_size], "conversation_id": conversation_id, "finished": False}
        yield f"data: {json.dumps(frame, ensure_ascii=False)}\n\n"
    yield f"data: {json.dumps({'delta': '', 'conversation_id': conversation_id, 'finished': True, 'message_id': message_id}, ensure_ascii=False)}\n\n"
    yield "data: [DONE]\n\n"


@router.get("/conversations", summary="我的会话列表")
def list_conversations(
    pq: PageQuery = Depends(page_query),
    scene: str = Query(default=""),
    current: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    stmt = select(AIConversation).where(AIConversation.user_id == current.user_id, AIConversation.is_deleted.is_(False))
    if scene:
        stmt = stmt.where(AIConversation.scene == scene)
    if pq.keyword:
        stmt = stmt.where(AIConversation.title.like(f"%{pq.keyword}%"))

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(AIConversation.updated_at.desc()).offset((pq.page - 1) * pq.page_size).limit(pq.page_size)
    ).all()
    return ok(page_result([ConversationBrief.model_validate(r).model_dump() for r in rows], pq.page, pq.page_size, total))


@router.get("/conversations/{conversation_id}", summary="会话详情（含完整消息流）")
def get_conversation(conversation_id: str, current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    row = _get_conversation(db, conversation_id, current.user_id)
    return ok(ConversationOut.model_validate(row).model_dump())


@router.delete("/conversations/{conversation_id}", summary="删除会话（软删除）")
def delete_conversation(conversation_id: str, current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    row = _get_conversation(db, conversation_id, current.user_id)
    row.is_deleted = True
    db.commit()
    return ok({"conversation_id": conversation_id, "deleted": True})


@router.post("/copywriting", summary="生成活动推文/宣传文案（PC 端管理后台）")
def copywriting(payload: CopywritingRequest, current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    text = llm_service.generate_copy(payload.topic, payload.style)
    conv = AIConversation(
        user_id=current.user_id,
        scene=ConversationScene.COPYWRITING.value,
        title=f"推文：{payload.topic}"[:120],
        book_id=None,
        model=llm_service.settings.LLM_MODEL,
        messages=[{"message_id": new_id("message"), "role": MessageRole.ASSISTANT.value, "content": text, "tokens": 0}],
        message_count=1,
        prompt_version=llm_service.settings.PROMPT_VERSION,
    )
    db.add(conv)
    db.commit()
    return ok({"conversation_id": conv.conversation_id, "content": text, "style": payload.style})
