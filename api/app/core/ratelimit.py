"""In-process rate limiting for the expensive endpoints.

Guards against *cost and resource exhaustion*: every Q&A turn and note-generation
request drives LLM calls (and, for Q&A, an embedding + vector scan).

Two flavours:

* :func:`rate_limit` — keyed by ``(scope, user_id)``; per authenticated account.
* :func:`rate_limit_by_ip` — keyed by ``(scope, client_ip)``; for endpoints that
  anonymous guests may call (guest Q&A), so one IP cannot run up spend.

Both are per-process, monotonic sliding windows returning 429 + ``Retry-After``.
Move to Redis / a shared store before scaling horizontally.
"""

from __future__ import annotations

import time
import uuid
from collections import deque
from typing import Callable

from fastapi import Depends, HTTPException, Request, status

from app.core.auth import get_current_user

# (scope, key) -> timestamps of calls still inside the window.
_WINDOWS: dict[tuple[str, str], deque[float]] = {}
# Cheap guard so the dict cannot grow without bound across many users.
_MAX_TRACKED_USERS = 20_000


def _hit(key: tuple[str, str], max_calls: int, window_seconds: float) -> None:
    now = time.monotonic()
    cutoff = now - window_seconds

    bucket = _WINDOWS.get(key)
    if bucket is None:
        if len(_WINDOWS) >= _MAX_TRACKED_USERS:
            _WINDOWS.clear()
        bucket = deque()
        _WINDOWS[key] = bucket

    while bucket and bucket[0] <= cutoff:
        bucket.popleft()

    if len(bucket) >= max_calls:
        retry_after = max(1, int(bucket[0] + window_seconds - now) + 1)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests — slow down and try again shortly.",
            headers={"Retry-After": str(retry_after)},
        )

    bucket.append(now)


def rate_limit(scope: str, max_calls: int, window_seconds: float) -> Callable:
    """Return a dependency enforcing ``max_calls`` per ``window_seconds`` per user."""

    async def _dependency(user_id: uuid.UUID = Depends(get_current_user)) -> None:
        _hit((scope, str(user_id)), max_calls, window_seconds)

    return _dependency


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    real = request.headers.get("x-real-ip")
    if real:
        return real.strip()
    return request.client.host if request.client else "unknown"


def rate_limit_by_ip(scope: str, max_calls: int, window_seconds: float) -> Callable:
    """Return a dependency enforcing ``max_calls`` per ``window_seconds`` per IP."""

    async def _dependency(request: Request) -> None:
        _hit((scope, _client_ip(request)), max_calls, window_seconds)

    return _dependency
