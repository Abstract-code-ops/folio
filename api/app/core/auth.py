"""Session validation against Better Auth table.

FastAPI validates protected requests by extracting the session token
from the Authorization header and querying the Better Auth ``session``
table directly via SQLAlchemy. No JWT secret is shared between processes.
"""

from __future__ import annotations

import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.db import get_async_session

# Better Auth stores sessions in a configurable table name
SESSION_TABLE = settings.better_auth_session_table  # "session"

bearer_scheme = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_async_session),
) -> uuid.UUID:
    """Resolve the authenticated user from the session token.

    Extracts the Bearer token from the Authorization header, looks it
    up in the Better Auth ``session`` table, and returns the ``user_id``.

    Raises 401 if the token is missing, expired, or invalid.
    """
    token = credentials.credentials

    # Query the Better Auth session table directly.
    # Table reference is dynamic because the name is configurable.
    query = text(
        f"SELECT user_id, expires_at FROM {SESSION_TABLE} WHERE id = :token"
    )
    result = await db.execute(query, {"token": token})
    row = result.one_or_none()

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid session token",
        )

    user_id_raw, expires_at = row

    if expires_at is not None:
        from datetime import datetime, timezone

        # expires_at may be naive or timezone-aware depending on the DB driver
        expires = expires_at
        if isinstance(expires, datetime):
            now = datetime.now(timezone.utc)
            if expires.tzinfo is None:
                now = now.replace(tzinfo=None)
            if expires < now:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Session token expired",
                )

    return uuid.UUID(str(user_id_raw))
