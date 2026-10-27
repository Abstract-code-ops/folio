"""Re-embed an existing book without re-parsing or re-annotating it.

Plan unit U7, step 5. This job recomputes **only** the embeddings, using the v2
inputs (breadcrumb plus the nomic document prefix). It deliberately imports no
parser and no metadata extractor:

- the metadata pass is the slow, rate-limited part of ingestion, and re-running
  it is what the re-embed job exists to avoid;
- the PDF is not read, so this works even if storage is unavailable;
- it is the cheap path for a future prefix or embedding-model change.

It does not fill chunk page ranges. Those come from a re-ingest (see
``api/scripts/reingest_book.py``); this job leaves them exactly as they are.
"""

from __future__ import annotations

import asyncio
import logging
import sys
import uuid
from collections.abc import Awaitable, Callable, Sequence
from typing import Optional

import dramatiq
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import SyncSessionLocal
from app.core.llm import embed_text
from app.models.chunk import Chunk
from app.models.section import Section
from app.pipeline.embed_inputs import (
    EMBED_VERSION,
    build_breadcrumb,
    chunk_embed_text,
    section_embed_text,
)

logger = logging.getLogger(__name__)

Embedder = Callable[[str], Awaitable[list[float]]]

# Guard against a corrupted parent chain looping forever.
_MAX_PARENT_DEPTH = 64


def log(message: str) -> None:
    logger.info(message)
    sys.stdout.flush()


def _breadcrumbs(sections: Sequence[Section]) -> dict[uuid.UUID, str]:
    """Heading path for each section, walking ``parent_section_id`` upwards."""
    by_id = {section.id: section for section in sections}
    cache: dict[uuid.UUID, str] = {}

    for section in sections:
        chain: list[str] = []
        cursor: Optional[Section] = section
        depth = 0
        while cursor is not None and depth < _MAX_PARENT_DEPTH:
            chain.append(cursor.heading)
            cursor = (
                by_id.get(cursor.parent_section_id)
                if cursor.parent_section_id is not None
                else None
            )
            depth += 1
        chain.reverse()
        cache[section.id] = build_breadcrumb(chain)

    return cache


async def reembed_book(
    db: Session,
    book_id: uuid.UUID,
    *,
    embedder: Embedder = embed_text,
) -> dict[str, int]:
    """Recompute embeddings for one book's sections and chunks.

    Returns counters. Makes no parser call and no metadata call.
    """
    sections = list(
        db.scalars(
            select(Section)
            .where(Section.book_id == book_id)
            .order_by(Section.chapter_index)
        )
    )
    if not sections:
        log(f"[REEMBED] No sections for book {book_id} - nothing to do")
        return {"sections": 0, "chunks": 0}

    breadcrumbs = _breadcrumbs(sections)
    chunk_total = 0

    for index, section in enumerate(sections, start=1):
        metadata = section.section_metadata or {}
        breadcrumb = breadcrumbs.get(section.id, "")

        section.embedding = await embedder(
            section_embed_text(
                breadcrumb=breadcrumb,
                summary=metadata.get("summary", ""),
                concepts=metadata.get("concepts") or [],
                raw_text=section.raw_text or "",
            )
        )
        section.embed_version = EMBED_VERSION

        chunks = list(
            db.scalars(
                select(Chunk)
                .where(Chunk.section_id == section.id)
                .order_by(Chunk.chunk_index)
            )
        )
        for chunk in chunks:
            chunk.embedding = await embedder(
                chunk_embed_text(breadcrumb, chunk.content)
            )
            chunk.embed_version = EMBED_VERSION
        chunk_total += len(chunks)

        if index % 10 == 0:
            db.flush()
            log(f"[REEMBED] {index}/{len(sections)} sections")

    db.commit()
    log(
        f"[REEMBED] Done: {len(sections)} sections, {chunk_total} chunks "
        f"at embed_version {EMBED_VERSION}"
    )
    return {"sections": len(sections), "chunks": chunk_total}


@dramatiq.actor(max_retries=2, min_backoff=30_000, max_backoff=120_000)
def reembed_book_task(book_id: str) -> None:
    """Dramatiq entry point for :func:`reembed_book`."""
    with SyncSessionLocal() as db:
        try:
            asyncio.run(reembed_book(db, uuid.UUID(book_id)))
        except Exception:
            db.rollback()
            logger.exception("Re-embed failed for book %s", book_id)
            raise
