"""Tests for the in-process per-user rate limiter (app/core/ratelimit.py)."""

from __future__ import annotations

import uuid

import pytest
from fastapi import HTTPException

from app.core import ratelimit


async def test_allows_up_to_limit():
    dep = ratelimit.rate_limit("t_allow", max_calls=2, window_seconds=60)
    uid = uuid.uuid4()
    await dep(user_id=uid)
    await dep(user_id=uid)  # second call, still within the limit


async def test_blocks_over_limit():
    dep = ratelimit.rate_limit("t_block", max_calls=1, window_seconds=60)
    uid = uuid.uuid4()
    await dep(user_id=uid)

    with pytest.raises(HTTPException) as exc:
        await dep(user_id=uid)

    assert exc.value.status_code == 429
    assert "Retry-After" in exc.value.headers


async def test_users_are_isolated():
    dep = ratelimit.rate_limit("t_iso", max_calls=1, window_seconds=60)
    a, b = uuid.uuid4(), uuid.uuid4()
    await dep(user_id=a)
    await dep(user_id=b)  # a different user is not blocked by a's burst


async def test_window_expiry_allows_again(monkeypatch):
    dep = ratelimit.rate_limit("t_exp", max_calls=1, window_seconds=60)
    uid = uuid.uuid4()
    await dep(user_id=uid)

    base = ratelimit.time.monotonic()
    monkeypatch.setattr(ratelimit.time, "monotonic", lambda: base + 61)

    await dep(user_id=uid)  # window elapsed -> allowed again
