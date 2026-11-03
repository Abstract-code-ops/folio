"""Book selection and ingestion business logic.

Books are shared global resources — library browsing does not require
authentication. All service functions accept an explicit db session and
return Pydantic models (not ORM instances) to enforce the API contract.

Ingestion runs **in this process** in a background thread (``run_ingest``):
the box has no separate Dramatiq worker, and the API container already runs
Ollama. ``run_ingest`` is the portable unit of work — moving ingestion to a
dedicated server later means calling that same function there and swapping
``trigger_ingestion`` to enqueue/message it.
"""

from __future__ import annotations

from datetime import datetime
import threading
import uuid
from typing import Optional

from pydantic import BaseModel, ConfigDict
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models.book import Book, IngestionStatus
from app.models.chunk import Chunk
from app.models.section import Section

# One ingestion at a time: the pipeline is CPU/Ollama heavy, and the figure
# captioner is rate-limited account-wide.
_INGEST_LOCK = threading.Lock()


# ── Pydantic response schemas ──────────────────────────────────


class BookResponse(BaseModel):
    """Public shape of a book returned to clients."""

    id: uuid.UUID
    title: str
    author: str
    category: Optional[str] = None
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


class IngestProgressResponse(BaseModel):
    """Live ingestion progress for the admin page (derived from row counts)."""

    book_id: uuid.UUID
    status: IngestionStatus
    sections_total: Optional[int] = None
    sections_done: int = 0
    chunks: int = 0
    figures: int = 0
    tables: int = 0
    word_count: Optional[int] = None
    running: bool = False


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


async def _count_chunks(db: AsyncSession, book_id: uuid.UUID, kind: str) -> int:
    return (
        await db.execute(
            select(func.count())
            .select_from(Chunk)
            .join(Section, Chunk.section_id == Section.id)
            .where(Section.book_id == book_id, Chunk.kind == kind)
        )
    ).scalar_one()


async def get_ingest_progress(
    db: AsyncSession,
    book_id: uuid.UUID,
) -> Optional[IngestProgressResponse]:
    """Live ingestion progress for a book, derived from row counts.

    Counts (sections, chunks, figures, tables) are read live, so the values stay
    accurate and survive the browser navigating away and back. ``figures``/
    ``tables`` tell you what the pipeline actually produced.
    """
    book = await db.get(Book, book_id)
    if book is None:
        return None

    sections_done = (
        await db.execute(
            select(func.count())
            .select_from(Section)
            .where(Section.book_id == book_id)
        )
    ).scalar_one()
    chunks = (
        await db.execute(
            select(func.count())
            .select_from(Chunk)
            .join(Section, Chunk.section_id == Section.id)
            .where(Section.book_id == book_id)
        )
    ).scalar_one()
    figures = await _count_chunks(db, book_id, "figure")
    tables = await _count_chunks(db, book_id, "table")

    return IngestProgressResponse(
        book_id=book_id,
        status=book.ingestion_status,
        sections_total=book.section_count,
        sections_done=sections_done,
        chunks=chunks,
        figures=figures,
        tables=tables,
        word_count=book.word_count,
        running=book.ingestion_status == IngestionStatus.PROCESSING,
    )


async def create_book(
    db: AsyncSession,
    *,
    title: str,
    author: str,
    category: Optional[str] = None,
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
        category=category,
        storage_url=storage_url,
        description=description,
        cover_image_url=cover_image_url,
        ingestion_status=IngestionStatus.NOT_STARTED,
    )
    db.add(book)
    await db.commit()
    await db.refresh(book)
    return BookResponse.model_validate(book)


async def delete_book(db: AsyncSession, book_id: uuid.UUID) -> bool:
    """Delete a book and all of its data. Returns False when it does not exist.

    ``section``/``chunk`` cascade from ``book`` (FK ``ON DELETE CASCADE``).
    ``coverage_event``, ``note_session`` (+ blocks/links) and ``qa_message``
    reference ``book_id`` with no FK (shared-resource invariant), so they are
    removed explicitly here to avoid orphans.
    """
    from app.models.coverage_event import CoverageEvent
    from app.models.note_block import NoteBlock
    from app.models.note_link import NoteLink
    from app.models.note_session import NoteSession
    from app.models.qa_message import QAMessage

    book = await db.get(Book, book_id)
    if book is None:
        return False

    note_ids = select(NoteSession.id).where(NoteSession.book_id == book_id)
    block_ids = select(NoteBlock.id).where(NoteBlock.note_id.in_(note_ids))
    await db.execute(delete(NoteLink).where(NoteLink.block_id.in_(block_ids)))
    await db.execute(delete(NoteBlock).where(NoteBlock.note_id.in_(note_ids)))
    await db.execute(delete(NoteSession).where(NoteSession.book_id == book_id))
    await db.execute(delete(CoverageEvent).where(CoverageEvent.book_id == book_id))
    await db.execute(delete(QAMessage).where(QAMessage.book_id == book_id))

    # Sections (and their chunks) delete via ON DELETE CASCADE.
    await db.delete(book)
    await db.commit()
    return True


async def trigger_ingestion(
    db: AsyncSession,
    book_id: uuid.UUID,
    *,
    force: bool = False,
) -> str:
    """Start ingestion for a book in a background thread.

    ``force=True`` re-runs an already-COMPLETED book (used to backfill tables /
    figures onto a book ingested by an older pipeline). It does this by setting
    the status to PROCESSING before the job starts, so ``run_ingest`` does not
    skip it; the pipeline's own checkpointing keeps the re-run cheap where
    sections are already complete.

    Only one ingest runs at a time (module lock).

    Returns:
        A job id string (``inline-<book_id>``).

    Raises:
        ValueError: If the book is not found, already ingested (without
            ``force``), or an ingest is already running.
    """
    from app.models.book import Book  # noqa: F811

    book = await db.get(Book, book_id)
    if book is None:
        raise ValueError(f"Book {book_id} not found")

    if book.ingestion_status == IngestionStatus.COMPLETED and not force:
        raise ValueError(
            f"Book {book_id} is already ingested — pass force to re-run it"
        )

    if not _INGEST_LOCK.acquire(blocking=False):
        raise ValueError("An ingestion is already running — try again when it finishes")

    # The portable unit of work. Swap this for an enqueue when ingestion moves
    # to a dedicated server; the pipeline itself does not change.
    from app.workers.ingest import run_ingest

    def _run() -> None:
        try:
            run_ingest(str(book_id))
        finally:
            _INGEST_LOCK.release()

    # Mark PROCESSING up front so the UI shows progress immediately AND so
    # run_ingest does not skip a COMPLETED book on a forced re-run.
    book.ingestion_status = IngestionStatus.PROCESSING
    await db.commit()
    threading.Thread(target=_run, name=f"ingest-{book_id}", daemon=True).start()

    return f"inline-{book_id}"


async def update_book_category(
    db: AsyncSession,
    book_id: uuid.UUID,
    category: Optional[str],
) -> Optional[BookResponse]:
    """Set (or clear) a book's category. Returns None if the book is missing."""
    book = await db.get(Book, book_id)
    if book is None:
        return None
    book.category = (category or "").strip() or None
    await db.commit()
    await db.refresh(book)
    return BookResponse.model_validate(book)
