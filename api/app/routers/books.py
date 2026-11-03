"""Book selection, ingestion status, and ingestion trigger route handlers.

Browse endpoints are unauthenticated — library browsing does not
require a user account (see docs/project-overview.md). Creating, deleting and
triggering ingestion are admin-only (see ``app.core.auth.require_admin``).

Reads use an AUTOCOMMIT session. The book list and a book's section tree are
shared, slow-changing data, so responses advertise a short public HTTP
Cache-Control window and the browser revalidates rather than re-querying on
every navigation.
"""

from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import require_admin
from app.core.db import get_async_session, get_read_session
from app.models.book import IngestionStatus
from app.services.books import (
    BookDetailResponse,
    BookListResponse,
    BookResponse,
    IngestProgressResponse,
    create_book,
    delete_book,
    get_book,
    get_ingest_progress,
    list_books,
    trigger_ingestion,
    update_book_category,
)

router = APIRouter(prefix="/books", tags=["books"])


class CreateBookRequest(BaseModel):
    """Request body for ``POST /books``."""

    title: str
    author: str
    category: Optional[str] = None
    description: Optional[str] = None
    cover_image_url: Optional[str] = None
    storage_url: str


class IngestionJobResponse(BaseModel):
    """Response returned after triggering a book ingestion job."""

    book_id: uuid.UUID
    job_id: str


@router.post("", response_model=BookResponse, status_code=201)
async def post_create_book(
    body: CreateBookRequest,
    _admin: uuid.UUID = Depends(require_admin),
    db: AsyncSession = Depends(get_async_session),
) -> BookResponse:
    """Add a new book to the open-access library."""
    return await create_book(
        db,
        title=body.title,
        author=body.author,
        category=body.category,
        storage_url=body.storage_url,
        description=body.description,
        cover_image_url=body.cover_image_url,
    )


@router.get("", response_model=BookListResponse)
async def get_books(
    response: Response,
    status: Optional[IngestionStatus] = Query(
        None,
        description="Filter by ingestion status",
    ),
    limit: int = Query(50, ge=1, le=200, description="Max results"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    db: AsyncSession = Depends(get_read_session),
) -> BookListResponse:
    """List all books, optionally filtered by ingestion status."""
    response.headers["Cache-Control"] = "public, max-age=30"

    return await list_books(db, status=status, limit=limit, offset=offset)


@router.get("/{book_id}", response_model=BookDetailResponse)
async def get_book_by_id(
    book_id: uuid.UUID,
    response: Response,
    load_sections: bool = Query(
        False,
        description="Eager-load section tree",
    ),
    db: AsyncSession = Depends(get_read_session),
) -> BookResponse:
    """Return a single book by ID."""
    response.headers["Cache-Control"] = "public, max-age=30"

    book = await get_book(db, book_id, load_sections=load_sections)
    if book is None:
        raise HTTPException(status_code=404, detail="Book not found")
    return book


@router.get("/{book_id}/ingest/status", response_model=IngestProgressResponse)
async def get_ingest_status(
    book_id: uuid.UUID,
    _admin: uuid.UUID = Depends(require_admin),
    db: AsyncSession = Depends(get_read_session),
) -> IngestProgressResponse:
    """Live ingestion progress for a book, for the admin ingest page.

    Counts (sections, chunks, figures, tables) come from the tables, so the
    values are accurate and survive the browser navigating away and back.
    Admin-only (the ingest trigger is admin-only too).
    """
    progress = await get_ingest_progress(db, book_id)
    if progress is None:
        raise HTTPException(status_code=404, detail="Book not found")
    return progress


@router.post("/{book_id}/ingest", response_model=IngestionJobResponse)
async def post_ingest_book(
    book_id: uuid.UUID,
    force: bool = Query(False, description="Re-run even if already ingested"),
    db: AsyncSession = Depends(get_async_session),
    _admin: uuid.UUID = Depends(require_admin),
) -> IngestionJobResponse:
    """Trigger background ingestion for a book (``?force=true`` to re-run)."""
    try:
        job_id = await trigger_ingestion(db, book_id, force=force)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return IngestionJobResponse(book_id=book_id, job_id=job_id)


@router.delete("/{book_id}", status_code=204)
async def delete_book_by_id(
    book_id: uuid.UUID,
    db: AsyncSession = Depends(get_async_session),
    _admin: uuid.UUID = Depends(require_admin),
) -> Response:
    """Delete a book and all of its data (admin only)."""
    deleted = await delete_book(db, book_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Book not found")
    return Response(status_code=204)


class UpdateBookCategoryRequest(BaseModel):
    """Request body for ``PATCH /books/{id}`` (category edit)."""

    category: Optional[str] = None


@router.patch("/{book_id}", response_model=BookResponse)
async def patch_book_category(
    book_id: uuid.UUID,
    body: UpdateBookCategoryRequest,
    db: AsyncSession = Depends(get_async_session),
    _admin: uuid.UUID = Depends(require_admin),
) -> BookResponse:
    """Set or clear a book's category (admin only)."""
    book = await update_book_category(db, book_id, body.category)
    if book is None:
        raise HTTPException(status_code=404, detail="Book not found")
    return book
