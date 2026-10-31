"""Book selection, ingestion status, and ingestion trigger route handlers.

Browse endpoints are unauthenticated — library browsing does not
require a user account (see docs/project-overview.md). The ingestion
trigger endpoint is authenticated since it initiates background work.

Reads use an AUTOCOMMIT session and a small in-process TTL cache: the book list
and a book's section tree are shared, slow-changing data, so caching removes
repeat DB round trips. The cache lives in the router (not the service) so
service unit tests are unaffected.
"""

from __future__ import annotations

import time
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.db import get_async_session, get_read_session
from app.models.book import IngestionStatus
from app.services.books import (
    BookDetailResponse,
    BookListResponse,
    BookResponse,
    create_book,
    get_book,
    list_books,
    trigger_ingestion,
)

router = APIRouter(prefix="/books", tags=["books"])

# Tiny TTL cache for library reads. Books change only on ingest, so a short TTL
# removes repeat round trips without needing explicit invalidation.
_CACHE_TTL = 30.0
_CACHE: dict[str, tuple[float, object]] = {}


def _cache_get(key: str) -> object | None:
    item = _CACHE.get(key)
    if item is not None and time.monotonic() - item[0] < _CACHE_TTL:
        return item[1]
    return None


def _cache_set(key: str, value: object) -> None:
    _CACHE[key] = (time.monotonic(), value)


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
    """Add a new book to the open-access library."""
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

    key = f"list:{status}:{limit}:{offset}"
    cached = _cache_get(key)
    if cached is not None:
        return cached  # type: ignore[return-value]

    result = await list_books(db, status=status, limit=limit, offset=offset)
    _cache_set(key, result)
    return result


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

    key = f"detail:{book_id}:{load_sections}"
    cached = _cache_get(key)
    if cached is not None:
        return cached  # type: ignore[return-value]

    book = await get_book(db, book_id, load_sections=load_sections)
    if book is None:
        raise HTTPException(status_code=404, detail="Book not found")
    _cache_set(key, book)
    return book


@router.post("/{book_id}/ingest", response_model=IngestionJobResponse)
async def post_ingest_book(
    book_id: uuid.UUID,
    db: AsyncSession = Depends(get_async_session),
    user_id: uuid.UUID = Depends(get_current_user),
) -> IngestionJobResponse:
    """Trigger background ingestion for a book."""
    try:
        job_id = await trigger_ingestion(db, book_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return IngestionJobResponse(book_id=book_id, job_id=job_id)
