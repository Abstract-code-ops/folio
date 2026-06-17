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
from app.core.litellm import embed_text_sync
from app.models.book import Book, IngestionStatus
from app.models.chunk import Chunk
from app.models.section import Section
from app.pipeline.chunker import chunk_section
from app.pipeline.metadata import extract_metadata
from app.pipeline.parser import parse_pdf

logger = logging.getLogger(__name__)


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

            # Idempotency check
            if book.ingestion_status == IngestionStatus.COMPLETED:
                logger.info("Book %s already ingested — skipping", book_id)
                return

            if book.ingestion_status == IngestionStatus.PROCESSING:
                logger.warning("Book %s is already being ingested — skipping", book_id)
                return

            # Mark as processing
            book.ingestion_status = IngestionStatus.PROCESSING
            db.commit()

            # Run the ingestion pipeline (async wrapped)
            asyncio.run(_run_pipeline(db, book))

        except Exception:
            book.ingestion_status = IngestionStatus.FAILED
            db.commit()
            logger.exception("Ingestion failed for book %s", book_id)
            raise


async def _run_pipeline(db: SyncSessionLocal, book: Book) -> None:
    """Core async pipeline: parse → chunk → embed → metadata → persist."""
    # 1. Parse PDF
    logger.info("Parsing PDF: %s", book.storage_url)
    parse_result = await parse_pdf(book.storage_url)

    total_sections = len(parse_result.sections)
    logger.info(
        "Parsed %d sections from '%s'",
        total_sections, parse_result.title,
    )

    # Update Book metadata from parse result if not already set
    if not book.title or book.title == "Unknown Title":
        book.title = parse_result.title
    if not book.author or book.author == "Unknown Author":
        book.author = parse_result.author

    # 2. Process each section: metadata → chunk → embed → persist
    for idx, parsed_sec in enumerate(parse_result.sections):
        logger.info(
            "Processing section %d/%d: %s",
            idx + 1, total_sections, parsed_sec.heading,
        )

        # 2a. Extract metadata (LLM call)
        metadata = await extract_metadata(
            heading=parsed_sec.heading,
            raw_text=parsed_sec.raw_text,
        )

        # 2b. Embed the section
        section_embedding = embed_text_sync(parsed_sec.heading + "\n" + parsed_sec.raw_text[:2000])

        # 2c. Create Section record
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
        db.flush()  # get section.id for chunks

        # 2d. Chunk the section text
        chunks = chunk_section(parsed_sec.raw_text)

        for chunk_result in chunks:
            # Embed each chunk
            chunk_embedding = embed_text_sync(chunk_result.content)

            chunk = Chunk(
                section_id=section.id,
                chunk_index=chunk_result.chunk_index,
                content=chunk_result.content,
                embedding=chunk_embedding,
            )
            db.add(chunk)

        # Flush periodically to avoid holding too many uncommitted records
        if idx % 10 == 0:
            db.flush()

    # 3. Update book with final counts
    book.section_count = total_sections
    book.word_count = parse_result.total_word_count
    book.ingestion_status = IngestionStatus.COMPLETED
    db.commit()

    logger.info(
        "Ingestion complete for book '%s': %d sections, %d words",
        book.title, total_sections, parse_result.total_word_count,
    )