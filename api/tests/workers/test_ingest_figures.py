"""Figure ingest-phase tests (Unit F).

Builds a synthetic PDF with a vector diagram (a drawn rectangle) and drives
``_ingest_figures`` with a fake caption generator, a no-op pacer and a fake
embedder — no provider, storage or database server.
"""

from __future__ import annotations

import fitz
from sqlalchemy import select

from app.models.book import Book
from app.models.chunk import Chunk
from app.models.section import Section
from app.pipeline.figure import QuotaExhausted
from app.pipeline.parser import ParsedSection, ParseResult
from app.workers import ingest


class _Pacer:
    async def acquire(self):
        return None


class _QuotaPacer:
    async def acquire(self):
        raise QuotaExhausted("quota")


def _book(session) -> Book:
    book = Book(title="Fig Book", author="T", storage_url="https://example.test/b.pdf")
    session.add(book)
    session.flush()
    return book


def _section(session, book) -> Section:
    section = Section(
        book_id=book.id,
        chapter_index=0,
        section_index=None,
        level=0,
        heading="Trees",
        page_start=1,
        page_end=1,
        raw_text="A section about trees and their diagrams.",
    )
    session.add(section)
    session.flush()
    return section


def _pdf_with_figure():
    doc = fitz.open()
    page = doc.new_page(width=600, height=800)
    shape = page.new_shape()
    shape.draw_rect(fitz.Rect(100, 100, 320, 320))
    shape.finish(color=(0, 0, 0), fill=(0.85, 0.85, 0.85), width=2)
    shape.commit()
    return doc


def _parse_result() -> ParseResult:
    return ParseResult(
        title="Fig Book",
        author="T",
        sections=[
            ParsedSection(
                heading="Trees",
                level=0,
                chapter_index=0,
                section_index=None,
                page_start=1,
                page_end=1,
                word_count=6,
                is_connective=False,
                raw_text="A section about trees and their diagrams.",
                blocks=[],
                parent_index=None,
            )
        ],
        total_word_count=6,
    )


async def _fake_embed(text: str) -> list[float]:
    return [0.1] * 768


async def test_ingest_figures_creates_a_figure_chunk(session) -> None:
    book = _book(session)
    _section(session, book)
    doc = _pdf_with_figure()

    seen_pngs: list[bytes] = []

    async def gen(prompt, png):
        seen_pngs.append(png)
        return "Reasoning.\n\nA diagram of a tree with three levels."

    created = await ingest._ingest_figures(
        session, book, _parse_result(), doc=doc, generator=gen, pacer=_Pacer(),
        embedder=_fake_embed,
    )

    assert created == 1
    chunk = session.scalars(select(Chunk).where(Chunk.kind == "figure")).one()
    assert chunk.content == "A diagram of a tree with three levels."
    assert chunk.page_start == 1
    assert chunk.bbox is not None and "x0" in chunk.bbox
    assert seen_pngs and seen_pngs[0][:8] == b"\x89PNG\r\n\x1a\n"  # real PNG bytes


async def test_ingest_figures_is_idempotent(session) -> None:
    book = _book(session)
    _section(session, book)
    doc = _pdf_with_figure()

    async def gen(prompt, png):
        return "A diagram."

    await ingest._ingest_figures(
        session, book, _parse_result(), doc=doc, generator=gen, pacer=_Pacer(),
        embedder=_fake_embed,
    )
    session.flush()

    again = await ingest._ingest_figures(
        session, book, _parse_result(), doc=doc, generator=gen, pacer=_Pacer(),
        embedder=_fake_embed,
    )
    assert again == 0


async def test_ingest_figures_soft_stops_on_quota(session) -> None:
    book = _book(session)
    _section(session, book)
    doc = _pdf_with_figure()

    async def gen(prompt, png):
        return "x"

    created = await ingest._ingest_figures(
        session, book, _parse_result(), doc=doc, generator=gen,
        pacer=_QuotaPacer(), embedder=_fake_embed,
    )
    assert created == 0
