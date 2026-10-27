"""Ingest v2 persistence tests (plan unit U7).

Drives ``persist_parse_result`` directly with a parsed result built by hand and a
fake embedder, so the test covers parent ids, chunk page ranges, the exact
embedding inputs and ``embed_version`` without a PDF, a database server or a
model call.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models.book import Book
from app.models.chunk import Chunk
from app.models.section import Section
from app.pipeline.parser import ParsedSection, ParseResult, TextBlock
from app.workers import ingest
from app.workers.ingest import persist_parse_result


def _words(count: int, prefix: str) -> str:
    return " ".join(f"{prefix}{i}" for i in range(count))


def _blocks(*pairs: tuple[int, str]) -> list[TextBlock]:
    return [
        TextBlock(
            page=page,
            bbox=(0.0, 0.0, 500.0, 40.0),
            text=text,
            block_type="text",
            from_ocr=False,
        )
        for page, text in pairs
    ]


def _parsed(
    *,
    heading: str,
    level: int,
    section_index,
    page_start: int,
    page_end: int,
    blocks: list[TextBlock],
    parent_index,
) -> ParsedSection:
    raw_text = "\n\n".join(block.text for block in blocks)
    return ParsedSection(
        heading=heading,
        level=level,
        chapter_index=0,
        section_index=section_index,
        page_start=page_start,
        page_end=page_end,
        word_count=len(raw_text.split()),
        is_connective=False,
        raw_text=raw_text,
        blocks=blocks,
        parent_index=parent_index,
    )


def _small_book() -> list[ParsedSection]:
    """Three sections, one per level, each with page-carrying blocks."""
    return [
        _parsed(
            heading="Part One",
            level=0,
            section_index=None,
            page_start=1,
            page_end=1,
            blocks=_blocks((1, _words(60, "part"))),
            parent_index=None,
        ),
        _parsed(
            heading="Chapter Two",
            level=1,
            section_index=0,
            page_start=2,
            page_end=3,
            blocks=_blocks((2, _words(60, "chapter")), (3, _words(60, "more"))),
            parent_index=0,
        ),
        _parsed(
            heading="Section Three",
            level=2,
            section_index=1,
            page_start=4,
            page_end=4,
            blocks=_blocks((4, _words(60, "section"))),
            parent_index=1,
        ),
    ]


class _Recorder:
    """Fake embedder that records every input string."""

    def __init__(self) -> None:
        self.inputs: list[str] = []

    async def __call__(self, text: str) -> list[float]:
        self.inputs.append(text)
        return [0.1, 0.2, 0.3]


@pytest.fixture
def fake_metadata(monkeypatch: pytest.MonkeyPatch):
    """Stub the metadata model out; return whatever the test wants."""

    async def stub(sections, **kwargs):
        return [
            {
                "summary": f"Summary of {heading}",
                "concepts": ["alpha", "beta"],
                "status": "ok",
            }
            for heading, _text in sections
        ]

    monkeypatch.setattr(ingest, "extract_metadata_batch", stub)
    return stub


def _book(session) -> Book:
    book = Book(
        title="Test Book",
        author="Tester",
        storage_url="https://example.test/book.pdf",
    )
    session.add(book)
    session.flush()
    return book


async def test_parent_ids_follow_the_parsed_hierarchy(session, fake_metadata) -> None:
    book = _book(session)

    await persist_parse_result(
        session, book, ParseResult(
            title="T", author="A", sections=_small_book(), total_word_count=180
        ),
        embedder=_Recorder(),
    )

    sections = list(
        session.scalars(select(Section).order_by(Section.chapter_index, Section.page_start))
    )
    assert len(sections) == 3
    part, chapter, section = sections
    assert part.parent_section_id is None
    assert chapter.parent_section_id == part.id
    assert section.parent_section_id == chapter.id


async def test_chunks_carry_page_ranges_from_their_blocks(session, fake_metadata) -> None:
    book = _book(session)

    await persist_parse_result(
        session, book, ParseResult(
            title="T", author="A", sections=_small_book(), total_word_count=180
        ),
        embedder=_Recorder(),
    )

    sections = {
        section.heading: section
        for section in session.scalars(select(Section))
    }

    chapter_chunks = list(
        session.scalars(
            select(Chunk)
            .where(Chunk.section_id == sections["Chapter Two"].id)
            .order_by(Chunk.chunk_index)
        )
    )
    assert chapter_chunks
    assert chapter_chunks[0].page_start == 2
    assert chapter_chunks[0].page_end == 3

    part_chunks = list(
        session.scalars(select(Chunk).where(Chunk.section_id == sections["Part One"].id))
    )
    assert (part_chunks[0].page_start, part_chunks[0].page_end) == (1, 1)


async def test_everything_written_is_at_embed_version_2(session, fake_metadata) -> None:
    book = _book(session)

    await persist_parse_result(
        session, book, ParseResult(
            title="T", author="A", sections=_small_book(), total_word_count=180
        ),
        embedder=_Recorder(),
    )

    assert all(
        section.embed_version == 2 for section in session.scalars(select(Section))
    )
    assert all(chunk.embed_version == 2 for chunk in session.scalars(select(Chunk)))


async def test_embedding_inputs_carry_the_prefix_and_breadcrumb(
    session, fake_metadata
) -> None:
    book = _book(session)
    recorder = _Recorder()

    await persist_parse_result(
        session, book, ParseResult(
            title="T", author="A", sections=_small_book(), total_word_count=180
        ),
        embedder=recorder,
    )

    assert recorder.inputs
    assert all(text.startswith("search_document: ") for text in recorder.inputs)

    # The nested section's breadcrumb is its full ancestor chain plus itself.
    assert any(
        text.startswith("search_document: Part One > Chapter Two > Section Three\n")
        for text in recorder.inputs
    ), recorder.inputs


async def test_stored_chunk_content_never_contains_the_prefix(
    session, fake_metadata
) -> None:
    book = _book(session)

    await persist_parse_result(
        session, book, ParseResult(
            title="T", author="A", sections=_small_book(), total_word_count=180
        ),
        embedder=_Recorder(),
    )

    for chunk in session.scalars(select(Chunk)):
        assert "search_document:" not in chunk.content
        assert "Part One >" not in chunk.content


async def test_section_metadata_is_reused_on_a_second_pass(
    session, fake_metadata
) -> None:
    book = _book(session)
    parsed = ParseResult(
        title="T", author="A", sections=_small_book(), total_word_count=180
    )

    first = await persist_parse_result(session, book, parsed, embedder=_Recorder())
    assert first["created"] == 3
    assert first["metadata_requested"] == 3

    # Second pass must update in place and skip the metadata model entirely.
    second = await persist_parse_result(session, book, parsed, embedder=_Recorder())
    assert second["created"] == 0
    assert second["updated"] == 3
    assert second["metadata_requested"] == 0
    assert second["metadata_reused"] == 3

    assert len(list(session.scalars(select(Section)))) == 3


async def test_a_second_pass_replaces_chunks_rather_than_duplicating_them(
    session, fake_metadata
) -> None:
    book = _book(session)
    parsed = ParseResult(
        title="T", author="A", sections=_small_book(), total_word_count=180
    )

    await persist_parse_result(session, book, parsed, embedder=_Recorder())
    first_count = len(list(session.scalars(select(Chunk))))

    await persist_parse_result(session, book, parsed, embedder=_Recorder())
    second_count = len(list(session.scalars(select(Chunk))))

    assert first_count == second_count


async def test_section_ids_survive_a_second_pass(session, fake_metadata) -> None:
    """Coverage events and Q&A rows point at section ids, so they must not churn."""
    book = _book(session)
    parsed = ParseResult(
        title="T", author="A", sections=_small_book(), total_word_count=180
    )

    await persist_parse_result(session, book, parsed, embedder=_Recorder())
    before = {s.heading: s.id for s in session.scalars(select(Section))}

    await persist_parse_result(session, book, parsed, embedder=_Recorder())
    after = {s.heading: s.id for s in session.scalars(select(Section))}

    assert before == after


# --------------------------------------------------------------------------
# Restartability
# --------------------------------------------------------------------------


async def test_a_second_pass_skips_sections_already_at_v2(session, fake_metadata) -> None:
    book = _book(session)
    parsed = ParseResult(
        title="T", author="A", sections=_small_book(), total_word_count=180
    )

    await persist_parse_result(session, book, parsed, embedder=_Recorder())
    second = await persist_parse_result(session, book, parsed, embedder=_Recorder())

    assert second["skipped"] == 3
    assert second["chunks"] == 0


async def test_skipping_makes_no_embedding_calls(session, fake_metadata) -> None:
    book = _book(session)
    parsed = ParseResult(
        title="T", author="A", sections=_small_book(), total_word_count=180
    )
    await persist_parse_result(session, book, parsed, embedder=_Recorder())

    recorder = _Recorder()
    await persist_parse_result(session, book, parsed, embedder=recorder)

    assert recorder.inputs == []


async def test_a_section_with_page_less_chunks_is_reprocessed(
    session, fake_metadata
) -> None:
    """The mixed v1/v2 state left by an interrupted run must be repaired."""
    book = _book(session)
    parsed = ParseResult(
        title="T", author="A", sections=_small_book(), total_word_count=180
    )
    await persist_parse_result(session, book, parsed, embedder=_Recorder())

    chapter = session.scalars(
        select(Section).where(Section.heading == "Chapter Two")
    ).one()
    chapter.embed_version = 1
    for chunk in session.scalars(
        select(Chunk).where(Chunk.section_id == chapter.id)
    ):
        chunk.page_start = None
        chunk.page_end = None
        chunk.embed_version = 1
    session.flush()

    second = await persist_parse_result(session, book, parsed, embedder=_Recorder())

    assert second["skipped"] == 2
    session.refresh(chapter)
    assert chapter.embed_version == 2
    rebuilt = list(session.scalars(select(Chunk).where(Chunk.section_id == chapter.id)))
    assert rebuilt
    assert all(chunk.page_start is not None for chunk in rebuilt)


async def test_no_resume_forces_a_full_rewrite(session, fake_metadata) -> None:
    book = _book(session)
    parsed = ParseResult(
        title="T", author="A", sections=_small_book(), total_word_count=180
    )
    await persist_parse_result(session, book, parsed, embedder=_Recorder())

    second = await persist_parse_result(
        session, book, parsed, embedder=_Recorder(), skip_completed=False
    )

    assert second["skipped"] == 0
    assert second["chunks"] > 0
