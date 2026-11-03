"""Debug figure captioning for one book (run inside the api container).

Usage:
    docker exec folio-api-1 python3 /app/scripts/debug_figures.py <book_id>

Runs a max-output-tokens sweep on the first couple of *real* figure regions so
you can see at which token cap Gemma starts returning non-empty text. If the
caption is empty at 200 but non-empty at 1024, the fix is to raise
``figure_max_tokens``.
"""

from __future__ import annotations

import asyncio
import sys
import uuid

import fitz
from sqlalchemy import select

from app.core.config import settings
from app.core.db import SyncSessionLocal
from app.models.book import Book
from app.models.section import Section
from app.pipeline import figure
from app.pipeline.parser import download_pdf

TOKEN_SWEEP = (200, 512, 1024, 2048)


def _section_for(sections, page: int):
    best = None
    for section in sections:
        if section.page_start is not None and section.page_end is not None:
            if section.page_start <= page <= section.page_end:
                best = section
    return best


async def main(book_id: str) -> None:
    bid = uuid.UUID(book_id)
    with SyncSessionLocal() as db:
        book = db.get(Book, bid)
        if book is None:
            print("book not found")
            return
        sections = sorted(
            db.scalars(select(Section).where(Section.book_id == bid)).all(),
            key=lambda s: (
                s.chapter_index,
                -1 if s.section_index is None else s.section_index,
                s.page_start,
            ),
        )

    pdf_bytes = await download_pdf(book.storage_url)
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    regions = figure.iter_figure_regions(
        doc,
        min_area_ratio=settings.figure_min_area_ratio,
        min_side=settings.figure_min_side,
        gap=settings.figure_cluster_gap,
    )
    print("model =", settings.figure_caption_model, "| regions:", len(regions))

    for page_no, bbox in regions[:2]:
        section = _section_for(sections, page_no)
        png = figure.crop_png(doc.load_page(page_no - 1), bbox, settings.figure_dpi)
        prompt = figure._build_caption_prompt(
            section.heading if section else "",
            (section.raw_text or "") if section else "",
        )
        print(f"\n--- page {page_no} | section={'yes' if section else 'NO'} | png={len(png)}B ---")
        for tokens in TOKEN_SWEEP:
            generator = figure.gemini_generator(
                model=settings.figure_caption_model, max_tokens=tokens
            )
            try:
                raw = await generator(prompt, png)
            except Exception as exc:  # noqa: BLE001
                print(f"  tokens={tokens:<5}: ERROR {type(exc).__name__}: {str(exc)[:120]}")
                continue
            cleaned = figure._clean_caption(raw)
            print(
                f"  tokens={tokens:<5}: raw_len={len(raw):<4} cleaned_len={len(cleaned):<4} "
                f"raw={raw[:100]!r}"
            )

    doc.close()


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1]))
