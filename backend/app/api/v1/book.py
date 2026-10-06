"""图书：馆藏/漂流主数据 + 扫码查书 + AI 推荐 + AI 深度解读。"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.v1.deps import page_query
from app.core.enums import BookSource, UserRole
from app.core.response import CODE_NOT_FOUND, BizError, ok, page_result
from app.core.security import CurrentUser, get_current_user, require_roles
from app.db.base import get_db
from app.db.models import AIConversation, Book
from app.schemas.book import (
    BookAnalysisResponse,
    BookCreate,
    BookOut,
    BookUpdate,
    RecommendItem,
    RecommendRequest,
    RecommendResponse,
)
from app.schemas.common import PageQuery
from app.services import llm_service

router = APIRouter(prefix="/books", tags=["图书"])


def _get_or_404(db: Session, book_id: str) -> Book:
    row = db.get(Book, book_id)
    if row is None or row.is_deleted:
        raise BizError(CODE_NOT_FOUND, "图书不存在")
    return row


@router.get("", summary="图书列表（分页 + 关键词/分类/来源筛选）")
def list_books(
    pq: PageQuery = Depends(page_query),
    category: str = Query(default=""),
    source: str = Query(default="", description="library / drift"),
    db: Session = Depends(get_db),
):
    stmt = select(Book).where(Book.is_deleted.is_(False))
    if pq.keyword:
        like = f"%{pq.keyword}%"
        stmt = stmt.where(or_(Book.title.like(like), Book.author.like(like), Book.isbn.like(like), Book.publisher.like(like)))
    if category:
        stmt = stmt.where(Book.category == category)
    if source:
        stmt = stmt.where(Book.source == source)

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    order_col = getattr(Book, pq.order_by, Book.updated_at)
    stmt = stmt.order_by(order_col.desc() if pq.order == "desc" else order_col.asc())
    rows = db.scalars(stmt.offset((pq.page - 1) * pq.page_size).limit(pq.page_size)).all()
    return ok(page_result([BookOut.model_validate(r).model_dump() for r in rows], pq.page, pq.page_size, total))


@router.get("/isbn/{isbn}", summary="按 ISBN 查书（小程序扫码入口）")
def get_by_isbn(isbn: str, db: Session = Depends(get_db)):
    clean = isbn.replace("-", "").strip()
    row = db.scalar(select(Book).where(Book.isbn == clean, Book.is_deleted.is_(False)))
    if row is None:
        raise BizError(CODE_NOT_FOUND, f"未找到 ISBN 为 {clean} 的图书，可发起漂流上架")
    return ok(BookOut.model_validate(row).model_dump())


@router.post("", summary="录入图书（管理端）", dependencies=[Depends(require_roles(UserRole.LIBRARIAN, UserRole.ADMIN))])
def create_book(payload: BookCreate, db: Session = Depends(get_db)):
    if db.scalar(select(Book).where(Book.isbn == payload.isbn)):
        raise BizError(1001, "该 ISBN 已存在")
    row = Book(**payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return ok(BookOut.model_validate(row).model_dump())


@router.get("/{book_id}", summary="图书详情（含 AI 解读缓存）")
def get_book(book_id: str, db: Session = Depends(get_db)):
    return ok(BookOut.model_validate(_get_or_404(db, book_id)).model_dump())


@router.patch("/{book_id}", summary="更新图书（管理端）", dependencies=[Depends(require_roles(UserRole.LIBRARIAN, UserRole.ADMIN))])
def update_book(book_id: str, payload: BookUpdate, db: Session = Depends(get_db)):
    row = _get_or_404(db, book_id)
    for k, v in payload.model_dump(exclude_none=True).items():
        setattr(row, k, v)
    db.commit()
    db.refresh(row)
    return ok(BookOut.model_validate(row).model_dump())


@router.post("/{book_id}/ai-summary", summary="生成/刷新 AI 书目深度解读")
def build_ai_summary(
    book_id: str,
    force_refresh: bool = Query(default=False, description="true 时忽略缓存重新生成"),
    current: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = _get_or_404(db, book_id)
    cached = bool(row.ai_summary) and not force_refresh
    if not cached:
        text, tags, _ = llm_service.analyze_book(row)
        row.ai_summary = text
        row.ai_tags = tags
        row.ai_summary_updated_at = datetime.now(timezone.utc)

    conv = AIConversation(
        user_id=current.user_id,
        scene="book_analysis",
        title=f"书目解读：{row.title}"[:120],
        book_id=row.book_id,
        book_title=row.title,
        model=llm_service.settings.LLM_MODEL,
        messages=[{"message_id": "msg_local", "role": "assistant", "content": row.ai_summary, "tokens": 0}],
        message_count=1,
        prompt_version=llm_service.settings.PROMPT_VERSION,
    )
    db.add(conv)
    db.commit()
    db.refresh(row)
    return ok(
        BookAnalysisResponse(
            book_id=row.book_id,
            ai_summary=row.ai_summary,
            ai_tags=row.ai_tags,
            cached=cached,
            conversation_id=conv.conversation_id,
            model=llm_service.settings.LLM_MODEL,
            prompt_version=llm_service.settings.PROMPT_VERSION,
        ).model_dump()
    )


@router.post("/recommend", summary="AI 智能推荐（PC 端智能推荐门户）")
def recommend_books(payload: RecommendRequest, current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    """推荐逻辑（第 1 轮简化版）：借阅热度榜 Top N + AI 生成推荐理由，后续再叠加个性化算法。"""
    rows = db.scalars(
        select(Book)
        .where(Book.is_deleted.is_(False), Book.source == BookSource.LIBRARY.value)
        .order_by(Book.borrow_count.desc(), Book.updated_at.desc())
        .limit(payload.limit)
    ).all()

    items = [
        RecommendItem(book=BookOut.model_validate(b), reason=llm_service.recommend_reason(b, i + 1, payload.extra_prompt))
        for i, b in enumerate(rows)
    ]
    conv = AIConversation(
        user_id=payload.user_id or current.user_id,
        scene="recommend",
        title="AI 智能推荐",
        book_id=None,
        model=llm_service.settings.LLM_MODEL,
        messages=[{"message_id": "msg_local", "role": "assistant", "content": "\n".join(i.reason for i in items), "tokens": 0}],
        message_count=1,
        prompt_version=llm_service.settings.PROMPT_VERSION,
    )
    db.add(conv)
    db.commit()
    return ok(
        RecommendResponse(
            conversation_id=conv.conversation_id,
            items=items,
            model=llm_service.settings.LLM_MODEL,
            prompt_version=llm_service.settings.PROMPT_VERSION,
        ).model_dump()
    )
