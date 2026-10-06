"""图书漂流：漂流池、扫码上架、申领交接（小程序端核心链路 / PC 端管理视图）。"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.v1.deps import page_query
from app.core.enums import BookSource, DriftStatus
from app.core.response import CODE_ILLEGAL_STATE, CODE_NOT_FOUND, BizError, ok, page_result
from app.core.security import CurrentUser, get_current_user, new_id
from app.db.base import get_db
from app.db.models import Book, DriftRecord, User
from app.schemas.book import BookOut
from app.schemas.common import PageQuery

router = APIRouter(prefix="/drift", tags=["图书漂流"])


class DriftOnShelfRequest(BaseModel):
    isbn: str = Field(description="扫码得到的 ISBN")
    owner_id: str = Field(default="", description="上架人，不传取当前用户")
    location: str = Field(default="", description="线下交接地点，如「图书馆一层大厅」")
    note: str = Field(default="", description="图书成色/备注")


@router.get("/books", summary="漂流池列表")
def list_drift_books(
    pq: PageQuery = Depends(page_query),
    drift_status: str = Query(default="", description="idle/reserved/in_transit/claimed/closed"),
    db: Session = Depends(get_db),
):
    stmt = select(Book).where(Book.is_deleted.is_(False), Book.source == BookSource.DRIFT.value)
    if pq.keyword:
        like = f"%{pq.keyword}%"
        stmt = stmt.where(or_(Book.title.like(like), Book.author.like(like), Book.isbn.like(like)))
    if drift_status:
        stmt = stmt.where(Book.drift_status == drift_status)

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(Book.updated_at.desc()).offset((pq.page - 1) * pq.page_size).limit(pq.page_size)
    ).all()
    return ok(page_result([BookOut.model_validate(r).model_dump() for r in rows], pq.page, pq.page_size, total))


@router.post("/books", summary="扫码上架一本漂流书")
def put_on_shelf(payload: DriftOnShelfRequest, current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    isbn = payload.isbn.replace("-", "").strip()
    owner_id = payload.owner_id or current.user_id

    book = db.scalar(select(Book).where(Book.isbn == isbn, Book.is_deleted.is_(False)))
    if book is None:
        # 新书：先建档再上架
        book = Book(
            isbn=isbn,
            title=f"待补充书名（{isbn}）",
            author="",
            source=BookSource.DRIFT.value,
            total_copies=1,
            available_copies=1,
            tags=[],
            ai_tags=[],
        )
        db.add(book)
        db.flush()
    else:
        book.source = BookSource.DRIFT.value

    book.drift_status = DriftStatus.IDLE.value
    book.current_holder_id = owner_id
    book.drift_location = payload.location
    book.drift_count = (book.drift_count or 0)

    record = DriftRecord(
        drift_id=new_id("drift"),
        book_id=book.book_id,
        holder_id=owner_id,
        from_user_id="",
        status=DriftStatus.IDLE.value,
        location=payload.location,
    )
    db.add(record)
    db.commit()
    db.refresh(book)
    return ok({"book": BookOut.model_validate(book).model_dump(), "drift_id": record.drift_id})


@router.post("/books/{book_id}/claim", summary="申领漂流书（生成交接记录）")
def claim(book_id: str, current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    book = db.get(Book, book_id)
    if book is None or book.is_deleted:
        raise BizError(CODE_NOT_FOUND, "漂流书不存在")
    if book.drift_status not in (DriftStatus.IDLE.value, DriftStatus.RESERVED.value):
        raise BizError(CODE_ILLEGAL_STATE, "该书当前状态不可申领")
    if book.current_holder_id == current.user_id:
        raise BizError(CODE_ILLEGAL_STATE, "不能申领自己上架的图书")

    prev_holder = book.current_holder_id
    book.current_holder_id = current.user_id
    book.drift_status = DriftStatus.CLAIMED.value
    book.drift_count = (book.drift_count or 0) + 1

    holder = db.get(User, current.user_id)
    record = DriftRecord(
        drift_id=new_id("drift"),
        book_id=book.book_id,
        holder_id=current.user_id,
        from_user_id=prev_holder,
        status=DriftStatus.CLAIMED.value,
        location=book.drift_location,
        claimed_at=datetime.now(timezone.utc),
    )
    db.add(record)
    db.commit()
    db.refresh(book)
    return ok(
        {
            "book": BookOut.model_validate(book).model_dump(),
            "drift_id": record.drift_id,
            "holder_name": holder.name if holder else "",
        }
    )


@router.get("/records", summary="漂流流转记录")
def list_records(
    pq: PageQuery = Depends(page_query),
    book_id: str = Query(default=""),
    db: Session = Depends(get_db),
):
    stmt = select(DriftRecord).where(DriftRecord.is_deleted.is_(False))
    if book_id:
        stmt = stmt.where(DriftRecord.book_id == book_id)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(DriftRecord.created_at.desc()).offset((pq.page - 1) * pq.page_size).limit(pq.page_size)
    ).all()
    items = [
        {
            "drift_id": r.drift_id,
            "book_id": r.book_id,
            "holder_id": r.holder_id,
            "from_user_id": r.from_user_id,
            "status": r.status,
            "location": r.location,
            "claimed_at": r.claimed_at,
            "created_at": r.created_at,
        }
        for r in rows
    ]
    return ok(page_result(items, pq.page, pq.page_size, total))


@router.get("/stats", summary="漂流数据概览（PC 端管理视图卡片）")
def drift_stats(db: Session = Depends(get_db)):
    base = select(func.count()).select_from(Book).where(Book.is_deleted.is_(False), Book.source == BookSource.DRIFT.value)
    return ok(
        {
            "total": db.scalar(base) or 0,
            "by_status": {s.value: db.scalar(base.where(Book.drift_status == s.value)) or 0 for s in DriftStatus},
        }
    )
