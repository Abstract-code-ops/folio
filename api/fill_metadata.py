"""Fill missing section metadata for a book from where it stopped.

Sections that already have non-empty metadata are skipped.
Sections with null/empty metadata get extracted in batches via Gemini.

Usage:
    docker compose exec api python3 /app/fill_metadata.py <book_id> [batch_size] [--model model_name]

Examples:
    docker compose exec api python3 /app/fill_metadata.py 62e581b4-9d31-4422-9100-7b6be671323d
    docker compose exec api python3 /app/fill_metadata.py 62e581b4-9d31-4422-9100-7b6be671323d 6
    docker compose exec api python3 /app/fill_metadata.py 62e581b4-9d31-4422-9100-7b6be671323d 6 --model gemini-3.1-flash-lite
"""

import asyncio
import logging
import sys
import uuid

from sqlalchemy import select

from app.core.config import settings
from app.core.db import SyncSessionLocal
from app.models.section import Section
from app.pipeline.metadata import extract_metadata_batch

logging.basicConfig(level=logging.INFO, force=True, format="%(message)s")
logger = logging.getLogger("fill_metadata")


async def main():
    if len(sys.argv) < 2:
        print("Usage: python3 fill_metadata.py <book_id> [batch_size] [--model model_name]")
        sys.exit(1)

    book_id = uuid.UUID(sys.argv[1])

    # Parse optional args — batch_size then optional --model
    batch_size = 10
    model_override = None
    args = sys.argv[2:]
    for i, arg in enumerate(args):
        if arg == "--model" and i + 1 < len(args):
            model_override = args[i + 1]
        elif arg != "--model" and not (i > 0 and args[i - 1] == "--model"):
            # If it's a positional arg before --model, it's the batch_size
            try:
                batch_size = int(arg)
            except ValueError:
                pass

    if model_override:
        # Temporarily override the config so metadata.py picks it up
        settings.gemini_metadata_model = model_override
        print(f"Using model: {model_override}")
    else:
        print(f"Using model: {settings.gemini_metadata_model} (from config)")

    with SyncSessionLocal() as db:
        # Find sections missing or with empty metadata
        # Fetch all sections; we'll filter in Python for simplicity
        all_sections = db.execute(
            select(Section).where(
                Section.book_id == book_id,
            ).order_by(Section.chapter_index, Section.section_index)
        ).scalars().all()

        def _is_empty_meta(meta):
            if meta is None or meta == {}:
                return True
            return not any([
                meta.get("concepts"),
                meta.get("summary"),
                meta.get("definitions"),
                meta.get("learning_objectives"),
            ])

        sections = [s for s in all_sections if _is_empty_meta(s.section_metadata)]

        if not sections:
            print("✓ All sections already have metadata — nothing to do.")
            return

        print(f"Found {len(sections)} sections needing metadata")

        # Skip connectives
        to_process = [(s.heading, s.raw_text) for s in sections if s.raw_text and not s.is_connective]
        skipped = len(sections) - len(to_process)
        if skipped:
            print(f"  ({skipped} connective sections skipped)")

        if not to_process:
            print("No sections need metadata (all are connectives or lack text)")
            return

        print(f"Processing {len(to_process)} sections in batches of {batch_size}...")
        print("")

        metadata_results = await extract_metadata_batch(
            to_process,
            batch_size=batch_size,
        )

        # Update sections that received metadata
        updated = 0
        meta_idx = 0
        for section in sections:
            if not section.raw_text or section.is_connective:
                continue
            meta = metadata_results[meta_idx]
            meta_idx += 1
            # Metadata now always carries a "status" key, so ``any(meta.values())``
            # is no longer a usable emptiness test - reuse the predicate that
            # selected the section in the first place.
            if meta and not _is_empty_meta(meta):
                section.section_metadata = meta
                updated += 1

        db.commit()
        print(f"\n✓ Updated {updated} sections with metadata")

        still_empty = sum(1 for s in sections if _is_empty_meta(s.section_metadata))
        failed = sum(
            1
            for s in sections
            if (s.section_metadata or {}).get("status") == "failed"
        )
        if still_empty:
            print(
                f"  {still_empty} sections still empty "
                f"({failed} explicitly failed after repair)"
            )
        else:
            print("  All sections now have metadata!")


if __name__ == "__main__":
    asyncio.run(main())
