"""Book ingestion background task definition.

Triggered when a book is selected for the first time. Orchestrates
the full pipeline — parse, chunk, embed, extract metadata — and
persists all records to the database.

Idempotency: the worker checks the book's ingestion status before
starting. If already completed, it exits early (no-op).
"""

from __future__ import annotations

import asyncio
import logging
import uuid

import dramatiq
from sqlalchemy import select

from app.core.db import SyncSessionLocal
from app.core.litellm import embed_text
from app.models.book import Book, IngestionStatus
from app.models.chunk import Chunk
from app.models.section import Section
from app.pipeline.chunker import chunk_section
from app.pipeline.metadata import extract_metadata_batch
from app.pipeline.parser import parse_pdf

logger = logging.getLogger(__name__)


def log(msg: str) -> None:
    """Log with immediate flush so we see progress in real time."""
    logger.info(msg)
    import sys
    sys.stdout.flush()


@dramatiq.actor(max_retries=2, min_backoff=30_000, max_backoff=120_000)
def ingest_book(book_id: str) -> None:
    """Ingest a book: parse → chunk → embed → metadata → persist.

    Args:
        book_id: UUID string of the ``Book`` to ingest.
    """
    parsed_id = uuid.UUID(book_id)

    with SyncSessionLocal() as db:
        try:
            book = db.get(Book, parsed_id)
            if book is None:
                logger.warning("Book %s not found — skipping ingestion", book_id)
                return

            if book.ingestion_status == IngestionStatus.COMPLETED:
                logger.info("Book %s already ingested — skipping", book_id)
                return

            if book.ingestion_status == IngestionStatus.PROCESSING:
                logger.warning("Book %s is already being ingested — skipping", book_id)
                return

            book.ingestion_status = IngestionStatus.PROCESSING
            db.commit()

            asyncio.run(_run_pipeline(db, book))

        except Exception:
            book.ingestion_status = IngestionStatus.FAILED
            db.commit()
            logger.exception("Ingestion failed for book %s", book_id)
            raise


async def _run_pipeline(db: SyncSessionLocal, book: Book) -> None:
    """Core async pipeline: parse → batch-metadata → chunk → embed → persist."""
    # ── STEP 1: Parse PDF ─────────────────────────────────────
    log("[PIPELINE] Step 1/5: Parsing PDF...")
    try:
        parse_result = await parse_pdf(book.storage_url)
        log(f"[PIPELINE] Step 1 OK: {len(parse_result.sections)} sections, {parse_result.total_word_count} words")
    except Exception as e:
        log(f"[PIPELINE] Step 1 FAILED: {e}")
        raise

    total_sections = len(parse_result.sections)

    if not book.title or book.title == "Unknown Title":
        book.title = parse_result.title
    if not book.author or book.author == "Unknown Author":
        book.author = parse_result.author
    db.flush()

    # ── STEP 2: Check for existing sections (resume support) ──
    log("[PIPELINE] Step 2/5: Checking for existing sections (resume)...")
    existing = set()
    try:
        if total_sections > 0:
            result = db.execute(
                select(Section.heading).where(
                    Section.book_id == book.id,
                    Section.heading.in_([s.heading for s in parse_result.sections]),
                )
            )
            existing = {row[0] for row in result.fetchall()}
        log(f"[PIPELINE] Step 2 OK: {len(existing)} sections already exist")
    except Exception as e:
        log(f"[PIPELINE] Step 2 FAILED: {e}")
        raise

    # ── STEP 3: Batch metadata extraction ─────────────────────
    log("[PIPELINE] Step 3/5: Preparing batch metadata...")
    try:
        sections_for_metadata: list[tuple[str, str]] = []
        for parsed_sec in parse_result.sections:
            if parsed_sec.heading in existing:
                continue
            if parsed_sec.is_connective:
                sections_for_metadata.append((parsed_sec.heading, ""))
                continue
            sections_for_metadata.append((parsed_sec.heading, parsed_sec.raw_text))

        to_skip = len(parse_result.sections) - len(sections_for_metadata)
        log(f"[PIPELINE] Step 3: {len(sections_for_metadata)} need metadata ({to_skip} skipped)")

        metadata_results: list[dict | None] = [None] * len(sections_for_metadata)
        if sections_for_metadata:
            log(f"[PIPELINE] Calling extract_metadata_batch (batch_size=10)...")
            metadata_results = await extract_metadata_batch(
                sections_for_metadata,
                batch_size=20,
            )
            log(f"[PIPELINE] Step 3 OK: {len(metadata_results)} metadata results")
        else:
            log("[PIPELINE] Step 3: All sections already have metadata — skipping")
    except Exception as e:
        log(f"[PIPELINE] Step 3 FAILED: {e}")
        raise

    # ── STEP 4: Process sections (create Section + Chunk + embed) ──
    log("[PIPELINE] Step 4/5: Processing sections (embed → chunk → persist)...")
    meta_idx = 0
    try:
        for idx, parsed_sec in enumerate(parse_result.sections):
            if parsed_sec.heading in existing:
                continue

            log(f"[PIPELINE]   Section {idx+1}/{total_sections}: '{parsed_sec.heading[:50]}'")

            # Get metadata
            metadata = metadata_results[meta_idx] if meta_idx < len(metadata_results) else {}
            if metadata is None:
                metadata = {}
            meta_idx += 1

            # Embed the section heading + text
            embed_input = parsed_sec.heading + "\n" + parsed_sec.raw_text[:2000]
            log(f"[PIPELINE]     Embedding section...")
            section_embedding = await embed_text(embed_input)

            # Create Section record
            section = Section(
                book_id=book.id,
                chapter_index=parsed_sec.chapter_index,
                section_index=parsed_sec.section_index,
                level=parsed_sec.level,
                heading=parsed_sec.heading,
                page_start=parsed_sec.page_start,
                page_end=parsed_sec.page_end,
                word_count=parsed_sec.word_count,
                is_connective=parsed_sec.is_connective,
                raw_text=parsed_sec.raw_text,
                section_metadata=metadata,
                embedding=section_embedding,
            )
            db.add(section)
            db.flush()
            log(f"[PIPELINE]     Section created: {section.id}")

            # Chunk the section text
            log(f"[PIPELINE]     Chunking...")
            chunks = chunk_section(parsed_sec.raw_text)
            log(f"[PIPELINE]     {len(chunks)} chunks")

            for ci, chunk_result in enumerate(chunks):
                log(f"[PIPELINE]       Embedding chunk {ci+1}/{len(chunks)} ({chunk_result.word_count} words)...")
                chunk_embedding = await embed_text(chunk_result.content)
                db.add(Chunk(
                    section_id=section.id,
                    chunk_index=chunk_result.chunk_index,
                    content=chunk_result.content,
                    embedding=chunk_embedding,
                ))

            # Checkpoint
            if idx > 0 and idx % 5 == 0:
                db.commit()
                log(f"[PIPELINE]     CHECKPOINT: committed up to section {idx+1}")

        log("[PIPELINE] Step 4 OK: All sections processed")
    except Exception as e:
        log(f"[PIPELINE] Step 4 FAILED at section {idx+1}: {e}")
        raise

    # ── STEP 5: Finalise book ─────────────────────────────────
    log("[PIPELINE] Step 5/5: Finalising book...")
    try:
        book.section_count = total_sections
        book.word_count = parse_result.total_word_count
        book.ingestion_status = IngestionStatus.COMPLETED
        db.commit()
        log(f"[PIPELINE] Step 5 OK: Book COMPLETED — {total_sections} sections, {parse_result.total_word_count} words")
    except Exception as e:
        log(f"[PIPELINE] Step 5 FAILED: {e}")
        raise
