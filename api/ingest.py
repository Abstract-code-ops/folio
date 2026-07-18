"""Run book ingestion from the terminal with a chosen Gemini model.

Usage:
    docker compose exec api python3 /app/ingest.py <book_id> <gemini_model>

Examples:
    docker compose exec api python3 /app/ingest.py 62e581b4-9d31-4422-9100-7b6be671323d gemini-2.0-flash
    docker compose exec api python3 /app/ingest.py 62e581b4-9d31-4422-9100-7b6be671323d gemini-2.5-flash-lite

Behaviour:
    - Parses the PDF (with OCR fallback for image-based pages)
    - If total extractable text is < 100 words across ALL sections, stops early
      with a clear error message (PDF is likely unreadable)
    - Chunks, embeds (Ollama/nomic), extracts metadata (Gemini), persists to DB
    - Handles Gemini rate limits with exponential backoff retry
    - Checkpoints every 5 sections so partial progress is saved
"""

import argparse
import asyncio
import logging
import sys
import uuid

logging.basicConfig(level=logging.INFO, force=True, format="%(message)s")
logger = logging.getLogger("ingest")


async def main():
    parser = argparse.ArgumentParser(description="Ingest a book into Folio")
    parser.add_argument("book_id", type=str, help="UUID of the book to ingest")
    parser.add_argument("model", type=str, help="Gemini model name (e.g. gemini-2.0-flash, gemini-2.5-flash-lite)")
    args = parser.parse_args()

    book_id = uuid.UUID(args.book_id)
    model = args.model

    # Override config so metadata pipeline uses the chosen model
    from app.core.config import settings
    settings.gemini_metadata_model = model
    logger.info(f"Using Gemini model: {model}")

    # ── Step 1: Parse PDF ─────────────────────────────────────
    logger.info("Parsing PDF...")
    from app.pipeline.parser import parse_pdf
    from app.core.db import SyncSessionLocal
    from app.models.book import Book, IngestionStatus

    with SyncSessionLocal() as db:
        book = db.get(Book, book_id)
        if book is None:
            logger.error(f"Book {book_id} not found")
            sys.exit(1)

        pdf_url = book.storage_url
        logger.info(f"PDF URL: {pdf_url}")

    parse_result = await parse_pdf(pdf_url)

    if parse_result.total_word_count < 100:
        logger.error("")
        logger.error("╔══════════════════════════════════════════════════════════════╗")
        logger.error("║  PDF PARSING FAILED                                       ║")
        logger.error("╠══════════════════════════════════════════════════════════════╣")
        logger.error(f"║  Total extractable text: {parse_result.total_word_count} words          ║")
        logger.error("║  The PDF appears to be image-based or uses an unsupported  ║")
        logger.error("║  format. Even OCR (Tesseract) could not extract text.      ║")
        logger.error("║                                                              ║")
        logger.error("║  Try a different PDF — most publisher PDFs (O'Reilly,      ║")
        logger.error("║  No Starch Press, Manning, MIT Press) have embedded text.  ║")
        logger.error("╚══════════════════════════════════════════════════════════════╝")
        logger.error("")
        sys.exit(1)

    logger.info(f"Parsed OK: {len(parse_result.sections)} sections, {parse_result.total_word_count} words")

    # ── Step 2: Ingest ────────────────────────────────────────
    logger.info("Starting ingestion pipeline...")

    with SyncSessionLocal() as db:
        book = db.get(Book, book_id)
        book.ingestion_status = IngestionStatus.PROCESSING
        db.commit()

        from app.workers.ingest import _run_pipeline
        await _run_pipeline(db, book)

    logger.info("")
    logger.info("✓ Ingestion complete!")
    logger.info(f"  Book: {parse_result.title}")
    logger.info(f"  Sections: {parse_result.total_word_count}")
    logger.info(f"  Words: {parse_result.total_word_count}")


if __name__ == "__main__":
    asyncio.run(main())
