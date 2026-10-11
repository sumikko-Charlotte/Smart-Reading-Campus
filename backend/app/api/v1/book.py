"""图书：馆藏/漂流主数据 + 扫码查书 + AI 推荐 + AI 深度解读。"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.v1.deps import page_query
from app.core.enums import BookSource, UserRole
from app.core.response import CODE_NOT_FOUND, CODE_SERVER_ERROR, BizError, ok, page_result
from app.core.security import CurrentUser, get_current_user, new_id, require_roles
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
from app.services.llm_service import LLMServiceError

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
    if pq.order_by not in {"title", "created_at", "updated_at", "publish_date", "borrow_count"}:
        raise BizError(1001, "order_by 不合法")
    order_col = getattr(Book, pq.order_by)
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


@router.post("", status_code=201, summary="录入图书（管理端）", dependencies=[Depends(require_roles(UserRole.LIBRARIAN, UserRole.ADMIN))])
def create_book(payload: BookCreate, db: Session = Depends(get_db)):
    if payload.isbn and db.scalar(select(Book).where(Book.isbn == payload.isbn, Book.is_deleted.is_(False))):
        raise BizError(1001, "该 ISBN 已存在")
    if payload.available_copies > payload.total_copies:
        raise BizError(1001, "可借册数不能超过馆藏总册数")
    row = Book(**payload.model_dump(), source=BookSource.LIBRARY.value)
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
    updates = payload.model_dump(exclude_unset=True)
    next_total = updates.get("total_copies", row.total_copies)
    next_available = updates.get("available_copies", row.available_copies)
    if next_total is not None and next_available is not None and next_available > next_total:
        raise BizError(1001, "可借册数不能超过馆藏总册数")
    for key, value in updates.items():
        if key in {"title", "author", "publisher", "category"} and value is None:
            raise BizError(1001, f"{key} 不允许为 null")
        if key == "publish_date" and value is not None:
            try:
                datetime.strptime(value, "%Y-%m-%d")
            except ValueError as exc:
                raise BizError(1001, "publish_date 必须为 YYYY-MM-DD") from exc
        if value is None and key in {"subtitle", "translator", "publisher", "category", "language", "cover_url", "summary"}:
            value = ""
        setattr(row, key, value)
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
        try:
            text, tags, _ = llm_service.analyze_book(row)
        except LLMServiceError as exc:
            raise BizError(CODE_SERVER_ERROR, str(exc), http_status=503) from exc
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
    """先按借阅热度选候选书，再由 DeepSeek 生成个性化推荐理由。"""
    rows = db.scalars(
        select(Book)
        .where(Book.is_deleted.is_(False), Book.source.in_([BookSource.LIBRARY.value, BookSource.BOTH.value]))
        .order_by(Book.borrow_count.desc(), Book.updated_at.desc())
        .limit(payload.limit)
    ).all()

    try:
        reasons, tokens = llm_service.recommend_reasons(rows, payload.extra_prompt, payload.limit)
    except LLMServiceError as exc:
        raise BizError(CODE_SERVER_ERROR, str(exc), http_status=503) from exc

    items = [RecommendItem(book=BookOut.model_validate(book), reason=reasons[book.book_id]) for book in rows]
    generated_at = datetime.now(timezone.utc).isoformat()
    recommendation_text = "\n".join(f"《{item.book.title}》：{item.reason}" for item in items)
    conv = AIConversation(
        user_id=current.user_id,
        scene="recommend",
        title="AI 智能推荐",
        book_id=None,
        model=llm_service.settings.LLM_MODEL,
        messages=[
            {
                "message_id": new_id("message"),
                "role": "assistant",
                "content": recommendation_text,
                "tokens": tokens,
                "created_at": generated_at,
            }
        ],
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
