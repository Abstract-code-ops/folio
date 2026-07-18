"""Book selection, ingestion status, and ingestion trigger route handlers.

Browse endpoints are unauthenticated — library browsing does not
require a user account (see project-overview.md). The ingestion
trigger endpoint is authenticated since it initiates background work.
"""

from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.db import get_async_session
from app.models.book import IngestionStatus
from app.services.books import (
    BookListResponse,
    BookResponse,
    create_book,
    get_book,
    list_books,
    trigger_ingestion,
)

router = APIRouter(prefix="/books", tags=["books"])


class CreateBookRequest(BaseModel):
    """Request body for ``POST /books``."""

    title: str
    author: str
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
    db: AsyncSession = Depends(get_async_session),
) -> BookResponse:
    """Add a new book to the open-access library.

    Books are shared global resources. The ingestion pipeline is not
    triggered here — call ``POST /books/{id}/ingest`` separately.
    """
    return await create_book(
        db,
        title=body.title,
        author=body.author,
        storage_url=body.storage_url,
        description=body.description,
        cover_image_url=body.cover_image_url,
    )


@router.get("", response_model=BookListResponse)
async def get_books(
    status: Optional[IngestionStatus] = Query(
        None,
        description="Filter by ingestion status",
    ),
    limit: int = Query(50, ge=1, le=200, description="Max results"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    db: AsyncSession = Depends(get_async_session),
) -> BookListResponse:
    """List all books, optionally filtered by ingestion status."""
    return await list_books(db, status=status, limit=limit, offset=offset)


@router.get("/{book_id}", response_model=BookResponse)
async def get_book_by_id(
    book_id: uuid.UUID,
    load_sections: bool = Query(
        False,
        description="Eager-load section tree",
    ),
    db: AsyncSession = Depends(get_async_session),
) -> BookResponse:
    """Return a single book by ID."""
    book = await get_book(db, book_id, load_sections=load_sections)
    if book is None:
        raise HTTPException(status_code=404, detail="Book not found")
    return book


@router.post("/{book_id}/ingest", response_model=IngestionJobResponse)
async def post_ingest_book(
    book_id: uuid.UUID,
    db: AsyncSession = Depends(get_async_session),
    user_id: uuid.UUID = Depends(get_current_user),
) -> IngestionJobResponse:
    """Trigger background ingestion for a book.

    Downloads the PDF, parses it into sections, chunks the text,
    embeds sections and chunks, and extracts structured metadata.
    Runs entirely in a Dramatiq background worker.

    Returns the job ID immediately for status polling.
    """
    try:
        job_id = await trigger_ingestion(db, book_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return IngestionJobResponse(book_id=book_id, job_id=job_id)
