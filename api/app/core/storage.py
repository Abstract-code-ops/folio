"""Supabase Storage client.

Minimal upload helper — used by ingestion to store an optimized (smaller) copy
of a large PDF and point ``book.storage_url`` at it so the in-browser viewer
gets a loadable file.
"""

from __future__ import annotations

import logging

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


def _base_url() -> str:
    return (settings.supabase_url or "").rstrip("/")


def _service_key() -> str:
    return settings.supabase_service_role_key or settings.supabase_key


def public_url(path: str, *, bucket: str | None = None) -> str:
    bucket = bucket or settings.supabase_storage_bucket
    return f"{_base_url()}/storage/v1/object/public/{bucket}/{path}"


async def upload_bytes(
    path: str,
    data: bytes,
    content_type: str = "application/pdf",
    *,
    bucket: str | None = None,
) -> str:
    """Upload ``data`` to ``bucket/path`` (upsert) and return the public URL.

    Raises ``RuntimeError`` when Supabase URL / service key are not configured;
    lets ``httpx.HTTPStatusError`` propagate on a failed upload.
    """
    bucket = bucket or settings.supabase_storage_bucket
    base = _base_url()
    key = _service_key()
    if not base or not key:
        raise RuntimeError("Supabase URL / service role key not configured")

    url = f"{base}/storage/v1/object/{bucket}/{path}"
    headers = {
        "Authorization": f"Bearer {key}",
        "x-upsert": "true",
        "Content-Type": content_type,
    }
    async with httpx.AsyncClient(timeout=180) as client:
        resp = await client.post(url, content=data, headers=headers)
        resp.raise_for_status()
    return public_url(path, bucket=bucket)
