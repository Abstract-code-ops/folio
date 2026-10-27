"""Book ingestion background task definition.

Triggered when a book is selected for the first time. Orchestrates the full
pipeline -- parse, metadata, chunk, embed -- and persists all records.

Persistence is an **upsert in document order**, not an insert-only pass:

- sections are written parent-before-child so ``parent_section_id`` can point at
  a real id, taken from the parser's ``parent_index``;
- an existing section at the same document position is updated in place rather
  than replaced, which keeps its id -- and therefore any coverage events or
  Q&A messages that reference it;
- its ``section_metadata`` is reused when the heading still matches, so a
  re-ingest does not repeat the slow, rate-limited metadata pass;
- chunks are rebuilt from scratch with page ranges and v2 embedding inputs.

**Restartable.** A section that is already at the current ``embed_version`` with
page-carrying chunks is skipped, so an interrupted run resumes where it stopped
instead of re-embedding completed work. Pass ``skip_completed=False`` to force a
full rewrite.
"""

from __future__ import annotations

import asyncio
import logging
import sys
import uuid
from collections.abc import Awaitable, Callable, Sequence
from typing import Optional

import dramatiq
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.db import SyncSessionLocal
from app.core.llm import embed_text
from app.models.book import Book, IngestionStatus
from app.models.chunk import Chunk
from app.models.section import Section
from app.pipeline.chunker import chunk_section
from app.pipeline.embed_inputs import (
    EMBED_VERSION,
    build_breadcrumb,
    chunk_embed_text,
    section_embed_text,
)
from app.pipeline.metadata import extract_metadata_batch
from app.pipeline.parser import ParsedSection, ParseResult, parse_pdf

logger = logging.getLogger(__name__)

# An embedder is any async callable text -> vector. Injectable for tests.
Embedder = Callable[[str], Awaitable[list[float]]]


def log(message: str) -> None:
    """Log with an immediate flush so progress is visible in real time."""
    logger.info(message)
    sys.stdout.flush()


# ── Document ordering helpers ─────────────────────────────────


def _doc_order(section: Section) -> tuple[int, int, int]:
    """Sort key reproducing parse order for stored sections."""
    return (
        section.chapter_index,
        -1 if section.section_index is None else section.section_index,
        section.page_start,
    )


def _existing_sections(db: Session, book_id: uuid.UUID) -> list[Section]:
    """Stored sections for a book, in document order."""
    rows = list(db.scalars(select(Section).where(Section.book_id == book_id)))
    rows.sort(key=_doc_order)
    return rows


def _reusable_metadata(
    existing: Sequence[Section],
    parsed: Sequence[ParsedSection],
) -> dict[int, dict]:
    """Map parsed index -> metadata already stored for that document position.

    Position plus heading is used rather than heading plus word count: parser v2
    legitimately changes word counts (it drops running headers and joins
    hyphenated lines), so an exact word-count match would reject nearly every
    section and force a full metadata re-run. Position is stable because the
    TOC itself has not changed.
    """
    reusable: dict[int, dict] = {}
    for index, (old, new) in enumerate(zip(existing, parsed)):
        if old.heading.strip() != new.heading.strip():
            continue
        metadata = old.section_metadata or {}
        if metadata:
            reusable[index] = metadata
    return reusable


def _ancestor_titles(parsed: Sequence[ParsedSection]) -> list[list[str]]:
    """Heading path for each section: ancestors first, then the section itself."""
    paths: list[list[str]] = []
    for section in parsed:
        chain: list[str] = []
        cursor: Optional[int] = section.parent_index
        guard = 0
        while cursor is not None and 0 <= cursor < len(parsed) and guard < 64:
            chain.append(parsed[cursor].heading)
            cursor = parsed[cursor].parent_index
            guard += 1
        chain.reverse()
        chain.append(section.heading)
        paths.append(chain)
    return paths


# ── Persistence ───────────────────────────────────────────────


def _is_complete(db: Session, section: Section) -> bool:
    """True when this section is already fully written at the current version.

    Used to make a re-ingest restartable: an interrupted run resumes instead of
    re-embedding work that is already committed. A section only counts as
    complete when its chunks exist, carry page ranges and are at the current
    ``embed_version``.
    """
    if (section.embed_version or 1) < EMBED_VERSION:
        return False
    chunks = list(db.scalars(select(Chunk).where(Chunk.section_id == section.id)))
    if not chunks:
        return False
    return all(
        chunk.page_start is not None and (chunk.embed_version or 1) >= EMBED_VERSION
        for chunk in chunks
    )


def _is_complete(db: Session, section: Section) -> bool:
    """True when this section is already fully written at the current version.

    A section only counts as complete when its chunks exist, carry page ranges,
    and are at the current ``embed_version``. Chunks with NULL pages would fail
    this, which is what forces a v1 book to be upgraded.
    """
    if (section.embed_version or 1) < EMBED_VERSION:
        return False
    chunks = list(db.scalars(select(Chunk).where(Chunk.section_id == section.id)))
    if not chunks:
        return False
    return all(
        chunk.page_start is not None and (chunk.embed_version or 1) >= EMBED_VERSION
        for chunk in chunks
    )


async def persist_parse_result(
    db: Session,
    book: Book,
    parse_result: ParseResult,
    *,
    embedder: Embedder = embed_text,
    reuse_metadata: bool = True,
    skip_completed: bool = True,
) -> dict[str, int]:
    """Write a parsed book to the database.

    Idempotent and restartable: running it twice leaves one row per document
    position, and a second run skips sections already at the current version.
    Returns counters for logging and tests.
    """
    parsed = parse_result.sections
    existing = _existing_sections(db, book.id)

    reused = _reusable_metadata(existing, parsed) if reuse_metadata else {}
    metadata_by_index: dict[int, dict] = dict(reused)

    to_request = [
        (index, section)
        for index, section in enumerate(parsed)
        if index not in metadata_by_index and not section.is_connective
    ]
    if to_request:
        log(f"[PIPELINE] Requesting metadata for {len(to_request)} section(s)...")
        results = await extract_metadata_batch(
            [(section.heading, section.raw_text) for _, section in to_request]
        )
        for (index, _section), result in zip(to_request, results):
            metadata_by_index[index] = result

    paths = _ancestor_titles(parsed)

    stats = {
        "created": 0,
        "updated": 0,
        "skipped": 0,
        "chunks": 0,
        "metadata_reused": len(reused),
        "metadata_requested": len(to_request),
        "stale": 0,
    }

    index_to_id: dict[int, uuid.UUID] = {}
    total = len(parsed)

    for index, section_data in enumerate(parsed):
        metadata = metadata_by_index.get(index, {})

        section = existing[index] if index < len(existing) else None
        if section is not None and section.heading.strip() != section_data.heading.strip():
            # The TOC no longer lines up at this position. Do not silently
            # retarget the old row; its coverage events point at it.
            log(
                "[PIPELINE] WARNING: position %d expected %r but stored row is %r - "
                "creating a new section" % (index, section_data.heading, section.heading)
            )
            section = None

        if section is None:
            section = Section(book_id=book.id)
            db.add(section)
            stats["created"] += 1
        else:
            stats["updated"] += 1

        section.chapter_index = section_data.chapter_index
        section.section_index = section_data.section_index
        section.level = section_data.level
        section.heading = section_data.heading
        section.page_start = section_data.page_start
        section.page_end = section_data.page_end
        section.word_count = section_data.word_count
        section.is_connective = section_data.is_connective
        section.raw_text = section_data.raw_text

        if metadata:
            section.section_metadata = metadata

        # Parent precedes child in document order, so its id already exists.
        parent_index = section_data.parent_index
        section.parent_section_id = (
            index_to_id.get(parent_index) if parent_index is not None else None
        )

        db.flush()  # assign an id before children reference it
        index_to_id[index] = section.id

        if skip_completed and _is_complete(db, section):
            stats["skipped"] += 1
            continue

        section.embed_version = EMBED_VERSION
        breadcrumb = build_breadcrumb(paths[index])
        section.embedding = await embedder(
            section_embed_text(
                breadcrumb=breadcrumb,
                summary=(metadata or {}).get("summary", ""),
                concepts=(metadata or {}).get("concepts") or [],
                raw_text=section_data.raw_text,
            )
        )

        # Chunks are rebuilt: their page ranges and inputs changed.
        db.execute(delete(Chunk).where(Chunk.section_id == section.id))
        chunks = chunk_section(section_data.raw_text, blocks=section_data.blocks)
        for chunk in chunks:
            db.add(
                Chunk(
                    section_id=section.id,
                    chunk_index=chunk.chunk_index,
                    content=chunk.content,
                    page_start=chunk.page_start,
                    page_end=chunk.page_end,
                    embedding=await embedder(
                        chunk_embed_text(breadcrumb, chunk.content)
                    ),
                    embed_version=EMBED_VERSION,
                )
            )
            stats["chunks"] += 1

        if index and index % 5 == 0:
            db.commit()
            log(
                f"[PIPELINE]   checkpoint {index + 1}/{total} sections "
                f"({stats['chunks']} chunks so far)"
            )

    stats["stale"] = max(0, len(existing) - len(parsed))
    if stats["stale"]:
        log(
            f"[PIPELINE] WARNING: {stats['stale']} stored section(s) are beyond the "
            "end of the parsed TOC and were left untouched"
        )

    db.commit()
    return stats


def _needs_upgrade(db: Session, book: Book) -> bool:
    """True when a book still has v1 embeddings or page-less chunks."""
    section = db.scalars(
        select(Section).where(Section.book_id == book.id).limit(1)
    ).first()
    if section is None:
        return True
    if (section.embed_version or 1) < EMBED_VERSION:
        return True
    chunk = db.scalars(
        select(Chunk)
        .join(Section, Chunk.section_id == Section.id)
        .where(Section.book_id == book.id)
        .limit(1)
    ).first()
    if chunk is not None and (
        chunk.page_start is None or (chunk.embed_version or 1) < EMBED_VERSION
    ):
        return True
    return False


async def run_pipeline(
    db: Session,
    book: Book,
    *,
    reuse_metadata: bool = True,
    skip_completed: bool = True,
) -> dict[str, int]:
    """Parse a book and persist it. Callable directly by the re-ingest script."""
    log(f"[PIPELINE] Parsing {book.title!r}...")
    parse_result = await parse_pdf(book.storage_url)
    log(
        f"[PIPELINE] Parsed {len(parse_result.sections)} sections, "
        f"{parse_result.total_word_count} words"
    )

    if not book.title or book.title == "Unknown Title":
        book.title = parse_result.title
    if not book.author or book.author == "Unknown Author":
        book.author = parse_result.author
    db.flush()

    stats = await persist_parse_result(
        db,
        book,
        parse_result,
        reuse_metadata=reuse_metadata,
        skip_completed=skip_completed,
    )

    book.section_count = len(parse_result.sections)
    book.word_count = parse_result.total_word_count
    book.ingestion_status = IngestionStatus.COMPLETED
    db.commit()

    log(
        "[PIPELINE] Done: %d created, %d updated, %d skipped, %d chunks, "
        "metadata reused=%d requested=%d"
        % (
            stats["created"],
            stats["updated"],
            stats["skipped"],
            stats["chunks"],
            stats["metadata_reused"],
            stats["metadata_requested"],
        )
    )
    return stats


@dramatiq.actor(max_retries=2, min_backoff=30_000, max_backoff=120_000)
def ingest_book(book_id: str) -> None:
    """Ingest a book: parse -> metadata -> chunk -> embed -> persist."""
    parsed_id = uuid.UUID(book_id)

    with SyncSessionLocal() as db:
        try:
            book = db.get(Book, parsed_id)
            if book is None:
                logger.warning("Book %s not found - skipping ingestion", book_id)
                return

            if book.ingestion_status == IngestionStatus.PROCESSING:
                logger.warning("Book %s is already being ingested - skipping", book_id)
                return

            if (
                book.ingestion_status == IngestionStatus.COMPLETED
                and not _needs_upgrade(db, book)
            ):
                logger.info("Book %s already ingested at v2 - skipping", book_id)
                return

            book.ingestion_status = IngestionStatus.PROCESSING
            db.commit()

            asyncio.run(run_pipeline(db, book))

        except Exception:
            book.ingestion_status = IngestionStatus.FAILED
            db.commit()
            logger.exception("Ingestion failed for book %s", book_id)
            raise
