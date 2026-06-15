"""Book selection and ingestion status route handlers.

Endpoints are unauthenticated — library browsing does not require
a user account (see project-overview.md).
"""

from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_async_session
from app.models.book import IngestionStatus
from app.services.books import (
    BookListResponse,
    BookResponse,
    get_book,
    list_books,
)

router = APIRouter(prefix="/books", tags=["books"])


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
