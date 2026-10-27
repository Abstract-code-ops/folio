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
from sqlalchemy import func, select
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
    storage_url: str
    ingestion_status: IngestionStatus
    section_count: Optional[int] = None
    word_count: Optional[int] = None
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class BookListResponse(BaseModel):
    """Wrapper for paginated / all book lists."""

    books: list[BookResponse]
    total: int


class BookSectionSummary(BaseModel):
    """Just enough of a section to answer \"which section is this page in\".

    Deliberately not the coverage map: that response carries aggregated scores
    for every section in the book and is far too heavy to resolve one page.
    """

    id: uuid.UUID
    heading: str
    page_start: int
    page_end: int
    level: int

    model_config = ConfigDict(from_attributes=True)


class BookDetailResponse(BookResponse):
    """A book, plus its section map when the caller asked for it."""

    sections: list[BookSectionSummary] = []

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

    # Fetch the page first: a page shorter than the limit proves there is
    # nothing after it, which makes the count query unnecessary. One fewer
    # round trip per library load, and here the round trip is the whole cost.
    result = await db.execute(query.limit(limit).offset(offset))
    books = result.scalars().unique().all()

    if len(books) < limit:
        total = offset + len(books)
    else:
        count_query = select(func.count()).select_from(Book)
        if status is not None:
            count_query = count_query.where(
                Book.ingestion_status == status
            )
        total = (await db.execute(count_query)).scalar_one()

    return BookListResponse(
        books=[BookResponse.model_validate(b) for b in books],
        total=total,
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

    # Sections are only read when they were eagerly loaded: touching the
    # relationship otherwise lazy-loads inside an async session and raises.
    if load_sections:
        detail = BookDetailResponse.model_validate(book)
        detail.sections.sort(key=lambda section: (section.page_start, section.page_end))
        return detail

    return BookDetailResponse(**BookResponse.model_validate(book).model_dump())


async def get_books_by_status(
    db: AsyncSession,
    status: IngestionStatus,
    *,
    limit: int = 50,
    offset: int = 0,
) -> BookListResponse:
    """Convenience wrapper — filter books by a single ingestion status."""
    return await list_books(db, status=status, limit=limit, offset=offset)


async def create_book(
    db: AsyncSession,
    *,
    title: str,
    author: str,
    storage_url: str,
    description: Optional[str] = None,
    cover_image_url: Optional[str] = None,
) -> BookResponse:
    """Create a new book record in the library.

    Books are shared global resources created once and shared across
    all users. The ingestion pipeline runs separately via
    :func:`trigger_ingestion`.

    Returns:
        ``BookResponse`` for the newly created book.
    """
    from app.models.book import Book, IngestionStatus  # noqa: F811

    book = Book(
        title=title,
        author=author,
        storage_url=storage_url,
        description=description,
        cover_image_url=cover_image_url,
        ingestion_status=IngestionStatus.NOT_STARTED,
    )
    db.add(book)
    await db.commit()
    await db.refresh(book)
    return BookResponse.model_validate(book)


async def trigger_ingestion(
    db: AsyncSession,
    book_id: uuid.UUID,
) -> str:
    """Trigger background ingestion for a book.

    Validates the book exists and is not already ingested or currently
    being ingested. Enqueues a Dramatiq ``ingest_book`` job and returns
    the job ID.

    Args:
        db: Async SQLAlchemy session.
        book_id: UUID of the book to ingest.

    Returns:
        Dramatiq job message ID as a string.

    Raises:
        ValueError: If the book is not found or already ingested.
    """
    from app.models.book import Book  # noqa: F811

    book = await db.get(Book, book_id)
    if book is None:
        raise ValueError(f"Book {book_id} not found")

    if book.ingestion_status == IngestionStatus.COMPLETED:
        raise ValueError(f"Book {book_id} is already ingested")

    if book.ingestion_status == IngestionStatus.PROCESSING:
        raise ValueError(f"Book {book_id} is currently being ingested")

    # Enqueue the ingestion job
    # Lazy import avoids pulling in Dramatiq broker at module load time
    from app.workers.ingest import ingest_book  # noqa: C0301
    job = ingest_book.send(str(book_id))

    # Mark as processing
    book.ingestion_status = IngestionStatus.PROCESSING
    await db.commit()

    return job.message_id
