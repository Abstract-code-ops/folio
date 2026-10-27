"""Re-ingest or re-embed a single book.

Run this on the host with ``docker exec``; the worker container must not be
started (a second Ollama takes the machine out of memory).

Two modes:

``--dry-run``      Parse the PDF and print statistics. Downloads the file and
                   holds it in memory, writes nothing to the database. Use this
                   first to see what parser v2 would do to a real book.

(default)          Full re-ingest: parse, reuse stored metadata, rebuild
                   sections, chunks, page ranges and v2 embeddings.

``--reembed-only`` Only recompute embeddings from rows already in the database.
                   No PDF download, no parser, no metadata model. Leaves chunk
                   page ranges untouched, so it cannot fill them.

Usage (from the host)::

    docker exec folio-api-1 python3 /app/scripts/reingest_book.py --list
    docker exec folio-api-1 python3 /app/scripts/reingest_book.py <book_id> --dry-run
    docker exec folio-api-1 python3 /app/scripts/reingest_book.py <book_id>
    docker exec folio-api-1 python3 /app/scripts/reingest_book.py <book_id> --reembed-only

Notes:

- Sections are updated in place, not deleted, so coverage events and Q&A
  messages that reference a section keep working.
- Stored ``section_metadata`` is reused when the heading still matches at the
  same document position. Pass ``--no-metadata-reuse`` to force a fresh
  metadata pass (slow, Gemini rate-limited).
- Embeddings written here carry ``embed_version = 2`` (nomic task prefixes plus
  breadcrumbs). Until U8 enables the query-side prefix, retrieval may be worse
  than before — measure with ``python3 -m evals.runner`` before and after.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import uuid
from pathlib import Path

# Make ``app`` importable when run as a plain file.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Without this, every progress line from the pipeline is swallowed: Python's
# root logger discards INFO when no handler is configured, so a long run looks
# frozen. Mirrors fill_metadata.py.
logging.basicConfig(level=logging.INFO, format="%(message)s", force=True)

from sqlalchemy import select  # noqa: E402

from app.core.db import SyncSessionLocal  # noqa: E402
from app.models.book import Book  # noqa: E402
from app.models.chunk import Chunk  # noqa: E402
from app.models.section import Section  # noqa: E402
from app.pipeline.parser import parse_pdf  # noqa: E402
from app.workers.ingest import run_pipeline  # noqa: E402
from app.workers.reembed import reembed_book  # noqa: E402


def _list_books() -> None:
    with SyncSessionLocal() as db:
        books = list(db.scalars(select(Book).order_by(Book.title)))
        if not books:
            print("No books in the database.")
            return
        print(f"{'id':38}  {'status':12}  {'sections':>8}  {'chunks':>7}  title")
        for book in books:
            section_count = len(
                list(db.scalars(select(Section.id).where(Section.book_id == book.id)))
            )
            chunk_count = len(
                list(
                    db.scalars(
                        select(Chunk.id)
                        .join(Section, Chunk.section_id == Section.id)
                        .where(Section.book_id == book.id)
                    )
                )
            )
            print(
                f"{book.id}  {book.ingestion_status.value:12}  "
                f"{section_count:8}  {chunk_count:7}  {book.title}"
            )


async def _dry_run(book: Book) -> int:
    """Parse only. Reports what parser v2 would produce."""
    result = await parse_pdf(book.storage_url)
    sections = result.sections
    if not sections:
        print("Parsed zero sections. Nothing to report.")
        return 1

    blocks = [block for section in sections for block in section.blocks]
    empty = [s for s in sections if not s.raw_text.strip()]
    inverted = [s for s in sections if s.page_end < s.page_start]
    with_parent = [s for s in sections if s.parent_index is not None]
    pages = [block.page for block in blocks]

    print(f"title:            {result.title}")
    print(f"author:           {result.author}")
    print(f"sections:         {len(sections)}")
    print(f"words:            {result.total_word_count}")
    print(f"blocks:           {len(blocks)}")
    print(f"pages covered:    {min(pages)}-{max(pages)}" if pages else "pages covered:    n/a")
    print(f"image blocks:     {sum(1 for b in blocks if b.block_type == 'image')}")
    print(f"ocr blocks:       {sum(1 for b in blocks if b.from_ocr)}")
    print(f"empty sections:   {len(empty)}")
    print(f"inverted ranges:  {len(inverted)}")
    print(f"sections w/ parent: {len(with_parent)}")
    print(f"connective:       {sum(1 for s in sections if s.is_connective)}")

    if empty:
        print("\nempty sections:")
        for section in empty[:10]:
            print(f"  pp.{section.page_start}-{section.page_end}  {section.heading[:60]}")
    print("\nNo database writes were made (--dry-run).")
    return 0


async def _reingest(
    db, book: Book, *, reuse_metadata: bool, skip_completed: bool
) -> int:
    await run_pipeline(
        db, book, reuse_metadata=reuse_metadata, skip_completed=skip_completed
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Re-ingest or re-embed one book (writes to the database unless --dry-run)."
    )
    parser.add_argument("book_id", nargs="?", help="UUID of the book")
    parser.add_argument("--list", action="store_true", help="list books and exit")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="parse and report only; writes nothing",
    )
    parser.add_argument(
        "--reembed-only",
        action="store_true",
        help="recompute embeddings only; no PDF, no parser, no metadata",
    )
    parser.add_argument(
        "--no-metadata-reuse",
        action="store_true",
        help="force a fresh metadata pass instead of reusing stored metadata",
    )
    parser.add_argument(
        "--no-resume",
        action="store_true",
        help="re-embed sections that are already at v2 instead of skipping them",
    )

    args = parser.parse_args(argv)
    if args.list:
        _list_books()
        return 0

    if not args.book_id:
        parser.error("a book_id is required unless --list is used")

    try:
        book_uuid = uuid.UUID(args.book_id)
    except ValueError:
        parser.error(f"{args.book_id!r} is not a UUID")

    with SyncSessionLocal() as db:
        book = db.get(Book, book_uuid)
        if book is None:
            print(f"No book with id {book_uuid}", file=sys.stderr)
            return 1

        print(f"book:   {book.title}")
        print(f"status: {book.ingestion_status.value}")
        print("")

        try:
            if args.dry_run:
                return asyncio.run(_dry_run(book))

            if args.reembed_only:
                stats = asyncio.run(reembed_book(db, book.id))
                print(f"sections re-embedded: {stats['sections']}")
                print(f"chunks re-embedded:   {stats['chunks']}")
                return 0

            asyncio.run(
                _reingest(
                    db,
                    book,
                    reuse_metadata=not args.no_metadata_reuse,
                    skip_completed=not args.no_resume,
                )
            )
            return 0
        except Exception as exc:  # surface the failure, leave a usable status
            db.rollback()
            print(f"FAILED: {exc}", file=sys.stderr)
            raise


if __name__ == "__main__":
    raise SystemExit(main())
