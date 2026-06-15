"""Book selection and ingestion business logic.

Books are shared global resources — library browsing does not require
authentication. All service functions accept an explicit db session and
return Pydantic models (not ORM instances) to enforce the API contract.
"""

from __future__ import annotations

from datetime import datetime
import uuid
from typing import Optional

from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models.book import Book, IngestionStatus


# ── Pydantic response schemas ──────────────────────────────────


class BookResponse(BaseModel):
    """Public shape of a book returned to clients."""

    id: uuid.UUID
    title: str
    author: str
    description: Optional[str] = None
    cover_image_url: Optional[str] = None
    ingestion_status: IngestionStatus
    section_count: Optional[int] = None
    word_count: Optional[int] = None
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class BookListResponse(BaseModel):
    """Wrapper for paginated / all book lists."""

    books: list[BookResponse]
    total: int


# ── Service functions ──────────────────────────────────────────


async def list_books(
    db: AsyncSession,
    *,
    status: Optional[IngestionStatus] = None,
    limit: int = 50,
    offset: int = 0,
) -> BookListResponse:
    """Return all books, optionally filtered by ingestion status.

    Library browsing is unauthenticated — no user_id required.
    Results ordered by title ascending.
    """
    query = select(Book).order_by(Book.title.asc())

    if status is not None:
        query = query.where(Book.ingestion_status == status)

    # Get total count before pagination
    count_query = select(Book.id).select_from(Book)
    if status is not None:
        count_query = count_query.where(Book.ingestion_status == status)
    total = (await db.execute(count_query)).scalars().all()
    total_count = len(total)

    # Paginated fetch
    query = query.limit(limit).offset(offset)
    result = await db.execute(query)
    books = result.scalars().unique().all()

    return BookListResponse(
        books=[BookResponse.model_validate(b) for b in books],
        total=total_count,
    )


async def get_book(
    db: AsyncSession,
    book_id: uuid.UUID,
    *,
    load_sections: bool = False,
) -> Optional[BookResponse]:
    """Return a single book by ID, or None if not found.

    Set *load_sections=True* to eager-load the section tree
    (useful when the coverage map is rendered alongside).
    """
    query = select(Book).where(Book.id == book_id)
    if load_sections:
        query = query.options(joinedload(Book.sections))

    result = await db.execute(query)
    book = result.scalars().unique().first()

    if book is None:
        return None

    return BookResponse.model_validate(book)


async def get_books_by_status(
    db: AsyncSession,
    status: IngestionStatus,
    *,
    limit: int = 50,
    offset: int = 0,
) -> BookListResponse:
    """Convenience wrapper — filter books by a single ingestion status."""
    return await list_books(db, status=status, limit=limit, offset=offset)
