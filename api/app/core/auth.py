"""Session validation against Better Auth table.

FastAPI validates protected requests by extracting the session token
from the Authorization header and querying the Better Auth ``session``
table directly via SQLAlchemy. No JWT secret is shared between processes.

TEMP: Returns a fixed anonymous user ID when no auth header is present,
so all endpoints work without auth until Better Auth is wired.
"""

from __future__ import annotations

import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.db import get_async_session

SESSION_TABLE = settings.better_auth_session_table

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_async_session),
) -> uuid.UUID:
    """Resolve the authenticated user, or return an anonymous ID if no token.

    TEMP: Returns a fixed anonymous user ID when no token is present,
    so all endpoints work without auth until Better Auth is wired.
    """
    if credentials is None:
        return uuid.UUID("00000000-0000-0000-0000-000000000001")

    token = credentials.credentials

    query = text(
        f"SELECT user_id, expires_at FROM {SESSION_TABLE} WHERE id = :token"
    )
    result = await db.execute(query, {"token": token})
    row = result.one_or_none()

    if row is None:
        return uuid.UUID("00000000-0000-0000-0000-000000000001")

    user_id_raw, expires_at = row

    if expires_at is not None:
        from datetime import datetime, timezone

        expires = expires_at
        if isinstance(expires, datetime):
            now = datetime.now(timezone.utc)
            if expires.tzinfo is None:
                now = now.replace(tzinfo=None)
            if expires < now:
                return uuid.UUID("00000000-0000-0000-0000-000000000001")

    return uuid.UUID(str(user_id_raw))
