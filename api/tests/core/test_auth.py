"""Tests for Better Auth session validation (app/core/auth.py).

Auth fails closed: ``settings.auth_required`` defaults to True, so a missing,
unknown, or expired token is a 401. The anonymous fallback is reachable only
when ``auth_required`` is False (development), and the app refuses to boot with
auth off in production (``config.enforce_auth_config``).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import text

from app.core import auth
from app.core.config import enforce_auth_config, settings


async def _make_session_table(db) -> None:
    await db.execute(
        text(
            "CREATE TABLE session ("
            "id TEXT PRIMARY KEY, token TEXT UNIQUE, "
            "user_id TEXT, expires_at TEXT)"
        )
    )


async def _insert(db, *, token: str, user_id: uuid.UUID, expires_at: str | None) -> None:
    await db.execute(
        text(
            "INSERT INTO session (id, token, user_id, expires_at) "
            "VALUES (:id, :token, :user_id, :expires_at)"
        ),
        {
            "id": str(uuid.uuid4()),
            "token": token,
            "user_id": str(user_id),
            "expires_at": expires_at,
        },
    )


def _creds(token: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


def _in(hours: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()


# ── Token lookup ──────────────────────────────────────────────


async def test_valid_token_returns_user(async_session, monkeypatch):
    monkeypatch.setattr(settings, "auth_required", True)
    await _make_session_table(async_session)
    user_id = uuid.uuid4()
    await _insert(async_session, token="tok-good", user_id=user_id, expires_at=_in(1))

    got = await auth.get_current_user(credentials=_creds("tok-good"), db=async_session)

    assert got == user_id


async def test_expired_token_rejected(async_session, monkeypatch):
    monkeypatch.setattr(settings, "auth_required", True)
    await _make_session_table(async_session)
    await _insert(async_session, token="tok-old", user_id=uuid.uuid4(), expires_at=_in(-1))

    with pytest.raises(HTTPException) as exc:
        await auth.get_current_user(credentials=_creds("tok-old"), db=async_session)

    assert exc.value.status_code == 401


async def test_unknown_token_rejected(async_session, monkeypatch):
    monkeypatch.setattr(settings, "auth_required", True)
    await _make_session_table(async_session)

    with pytest.raises(HTTPException) as exc:
        await auth.get_current_user(credentials=_creds("tok-missing"), db=async_session)

    assert exc.value.status_code == 401


async def test_no_header_rejected_when_required(async_session, monkeypatch):
    monkeypatch.setattr(settings, "auth_required", True)

    with pytest.raises(HTTPException) as exc:
        await auth.get_current_user(credentials=None, db=async_session)

    assert exc.value.status_code == 401


async def test_null_expiry_is_accepted(async_session, monkeypatch):
    monkeypatch.setattr(settings, "auth_required", True)
    await _make_session_table(async_session)
    user_id = uuid.uuid4()
    await _insert(async_session, token="tok-noexp", user_id=user_id, expires_at=None)

    got = await auth.get_current_user(credentials=_creds("tok-noexp"), db=async_session)

    assert got == user_id


# ── Anonymous fallback (development only) ────────────────────


async def test_no_header_returns_anonymous_when_optional(async_session, monkeypatch):
    monkeypatch.setattr(settings, "auth_required", False)

    got = await auth.get_current_user(credentials=None, db=async_session)

    assert got == auth.ANONYMOUS_USER_ID


async def test_unknown_token_returns_anonymous_when_optional(async_session, monkeypatch):
    monkeypatch.setattr(settings, "auth_required", False)
    await _make_session_table(async_session)

    got = await auth.get_current_user(credentials=_creds("tok-missing"), db=async_session)

    assert got == auth.ANONYMOUS_USER_ID


# ── Fail-closed startup guard ────────────────────────────────


def test_guard_refuses_auth_off_in_production(monkeypatch):
    monkeypatch.setenv("ENV", "production")
    monkeypatch.setattr(settings, "auth_required", False)

    with pytest.raises(RuntimeError):
        enforce_auth_config()


def test_guard_allows_auth_on_in_production(monkeypatch):
    monkeypatch.setenv("ENV", "production")
    monkeypatch.setattr(settings, "auth_required", True)

    enforce_auth_config()  # must not raise


def test_guard_allows_auth_off_in_development(monkeypatch):
    monkeypatch.delenv("ENV", raising=False)
    monkeypatch.setattr(settings, "environment", "development")
    monkeypatch.setattr(settings, "auth_required", False)

    enforce_auth_config()  # must not raise


# ── Admin authorization (require_admin) ─────────────────────


async def _make_user_table(db) -> None:
    await db.execute(text('CREATE TABLE "user" (id TEXT PRIMARY KEY, email TEXT)'))


async def _insert_user(db, *, user_id: uuid.UUID, email: str) -> None:
    await db.execute(
        text('INSERT INTO "user" (id, email) VALUES (:id, :email)'),
        {"id": str(user_id), "email": email},
    )


async def test_require_admin_allows_listed_email(async_session, monkeypatch):
    monkeypatch.setattr(settings, "admin_emails", "aa2933395@gmail.com")
    await _make_user_table(async_session)
    user_id = uuid.uuid4()
    # Case-insensitive match: stored mixed-case, allow-list lowercase.
    await _insert_user(async_session, user_id=user_id, email="AA2933395@gmail.com")

    got = await auth.require_admin(user_id=user_id, db=async_session)

    assert got == user_id


async def test_require_admin_rejects_unlisted_email(async_session, monkeypatch):
    monkeypatch.setattr(settings, "admin_emails", "aa2933395@gmail.com")
    await _make_user_table(async_session)
    user_id = uuid.uuid4()
    await _insert_user(async_session, user_id=user_id, email="someone@example.com")

    with pytest.raises(HTTPException) as exc:
        await auth.require_admin(user_id=user_id, db=async_session)

    assert exc.value.status_code == 403


async def test_require_admin_rejects_unknown_user(async_session, monkeypatch):
    monkeypatch.setattr(settings, "admin_emails", "aa2933395@gmail.com")
    await _make_user_table(async_session)

    with pytest.raises(HTTPException) as exc:
        await auth.require_admin(user_id=uuid.uuid4(), db=async_session)

    assert exc.value.status_code == 403


async def test_require_admin_rejects_when_allowlist_empty(async_session, monkeypatch):
    monkeypatch.setattr(settings, "admin_emails", "")

    with pytest.raises(HTTPException) as exc:
        await auth.require_admin(user_id=uuid.uuid4(), db=async_session)

    assert exc.value.status_code == 403
