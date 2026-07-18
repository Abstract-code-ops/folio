"""Coverage map retrieval and event emission route handlers.

All endpoints are authenticated — coverage data is user-scoped.
The current user is resolved from the session token at the router
level and passed explicitly to service functions.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.db import get_async_session
from app.services.coverage import CoverageMapResponse, get_coverage_map

router = APIRouter(prefix="/coverage", tags=["coverage"])


@router.get("/{book_id}", response_model=CoverageMapResponse)
async def get_book_coverage(
    book_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> CoverageMapResponse:
    """Return the full coverage map for *book_id*."""
    return await get_coverage_map(db, user_id, book_id)
