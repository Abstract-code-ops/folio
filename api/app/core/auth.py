"""Session validation against the Better Auth ``session`` table.

FastAPI validates protected requests by extracting the session token from the
``Authorization`` header and querying Better Auth's ``session`` table directly
via SQLAlchemy. No JWT secret is shared between processes.

Two details matter and are easy to get wrong:

* Better Auth stores the session cookie/token in a dedicated ``token`` column,
  **not** in the row ``id``. The lookup is therefore ``WHERE token = :token``
  (column name configurable via ``better_auth_session_token_column``).
* Better Auth's default column names are camelCase. The table is expected to be
  mapped to snake_case (``user_id``/``expires_at``), matching this repo.

Fail-closed: ``settings.auth_required`` defaults to True. When true, a missing,
unknown, or expired token is rejected with 401. When false (local development
only — the app refuses to boot with auth off in production, see
``config.enforce_auth_config``), requests without a valid token fall back to a
fixed anonymous user id so the app stays usable before auth is wired.

Token cache: each request to a protected endpoint used to cost one DB round trip
(expensive against a remote database). Resolved tokens are cached in-process for
``_TOKEN_CACHE_TTL`` seconds, so repeat requests within that window skip the
query. The session's own expiry is still enforced from the cached value. The
trade-off is that a revoked/signed-out session keeps authenticating for at most
that TTL — keep it short.
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.db import get_read_session

ANONYMOUS_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")

_TOKEN_CACHE_TTL = 30.0
# token -> (user_id, session-expiry epoch seconds or 0, cached_at monotonic)
_TOKEN_CACHE: dict[str, tuple[uuid.UUID, float, float]] = {}

bearer_scheme = HTTPBearer(auto_error=False)


def _unauthorized(detail: str = "Not authenticated") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def _anonymous_or_reject() -> uuid.UUID:
    """Anonymous identity when auth is optional; 401 when it is required."""
    if settings.auth_required:
        raise _unauthorized()
    return ANONYMOUS_USER_ID


def _as_datetime(expires_at: object) -> datetime | None:
    if expires_at is None:
        return None
    if isinstance(expires_at, str):
        try:
            expires_at = datetime.fromisoformat(expires_at)
        except ValueError:
            return None
    if not isinstance(expires_at, datetime):
        return None
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return expires_at


def _is_expired(expires_at: object) -> bool:
    """True when a session expiry has passed.

    Handles both ``datetime`` (Postgres) and ISO-8601 ``str`` (SQLite in tests).
    A missing or unparseable value is treated as not-expired.
    """
    expires = _as_datetime(expires_at)
    if expires is None:
        return False
    return expires < datetime.now(timezone.utc)


def _expiry_epoch(expires_at: object) -> float:
    expires = _as_datetime(expires_at)
    return expires.timestamp() if expires is not None else 0.0


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_read_session),
) -> uuid.UUID:
    """Resolve the authenticated user id, or reject when auth is required."""
    if credentials is None:
        return _anonymous_or_reject()

    token = credentials.credentials
    now = time.monotonic()

    cached = _TOKEN_CACHE.get(token)
    if cached is not None:
        user_id, expiry_epoch, cached_at = cached
        if now - cached_at < _TOKEN_CACHE_TTL and (
            expiry_epoch == 0 or expiry_epoch > time.time()
        ):
            return user_id
        _TOKEN_CACHE.pop(token, None)

    table = settings.better_auth_session_table
    token_column = settings.better_auth_session_token_column

    # Table/column names come from trusted config, never from user input, so
    # interpolating them is safe; the token itself is a bound parameter.
    query = text(
        f"SELECT user_id, expires_at FROM {table} WHERE {token_column} = :token"
    )
    result = await db.execute(query, {"token": token})
    row = result.one_or_none()

    if row is None:
        return _anonymous_or_reject()

    user_id_raw, expires_at = row

    if _is_expired(expires_at):
        return _anonymous_or_reject()

    try:
        user_id = uuid.UUID(str(user_id_raw))
    except (ValueError, AttributeError):
        # A non-UUID id (e.g. a legacy nanoid) would otherwise 500 the request.
        return _anonymous_or_reject()

    _TOKEN_CACHE[token] = (user_id, _expiry_epoch(expires_at), now)
    return user_id
