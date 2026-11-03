"""Run book ingestion from the terminal.

Usage:
    docker compose exec api python3 /app/ingest.py <book_id> [gemini_model]

Examples:
    docker compose exec api python3 /app/ingest.py 62e581b4-...-7b6be671323d gemini-2.5-flash-lite

This runs the SAME pipeline the API uses (``run_pipeline`` — parse, chunk,
embed, metadata, tables, figure captions) but in the foreground, so every
``[PIPELINE] …`` log line is printed live. Use it to see exactly where a book
fails (e.g. "could not download PDF", "0 words", "Detected N figure regions").
"""

import argparse
import asyncio
import logging
import sys
import uuid

logging.basicConfig(level=logging.INFO, force=True, format="%(message)s")
logger = logging.getLogger("ingest")


async def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest a book into Folio")
    parser.add_argument("book_id", type=str, help="UUID of the book to ingest")
    parser.add_argument(
        "model",
        type=str,
        nargs="?",
        default=None,
        help="Optional Gemini model override (e.g. gemini-2.5-flash-lite)",
    )
    args = parser.parse_args()

    book_id = uuid.UUID(args.book_id)

    from app.core.config import settings
    from app.core.db import SyncSessionLocal
    from app.models.book import Book, IngestionStatus
    from app.workers.ingest import run_pipeline

    if args.model:
        settings.gemini_metadata_model = args.model
        logger.info("Using Gemini model: %s", args.model)

    with SyncSessionLocal() as db:
        book = db.get(Book, book_id)
        if book is None:
            logger.error("Book %s not found", book_id)
            sys.exit(1)

        logger.info("PDF URL: %s", book.storage_url)
        logger.info("Current status: %s", book.ingestion_status)

        book.ingestion_status = IngestionStatus.PROCESSING
        db.commit()

        try:
            stats = await run_pipeline(db, book)
        except Exception:
            book.ingestion_status = IngestionStatus.FAILED
            db.commit()
            logger.exception("Ingestion failed")
            sys.exit(1)

        logger.info("")
        logger.info("✓ Ingestion complete")
        logger.info("  sections: %s  words: %s", book.section_count, book.word_count)
        logger.info("  stats: %s", stats)


if __name__ == "__main__":
    asyncio.run(main())
