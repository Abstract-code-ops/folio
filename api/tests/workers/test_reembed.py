"""Re-embed job tests (plan unit U7, step 5).

The contract worth protecting: ``reembed_book`` recomputes embeddings and
nothing else. It must not parse the PDF or call the metadata model, and it must
not invent chunk page ranges it did not receive.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models.book import Book
from app.models.chunk import Chunk
from app.models.section import Section
from app.pipeline import metadata as metadata_module
from app.pipeline import parser as parser_module
from app.workers.reembed import reembed_book


class _Recorder:
    def __init__(self) -> None:
        self.inputs: list[str] = []

    async def __call__(self, text: str) -> list[float]:
        self.inputs.append(text)
        return [0.5, 0.5, 0.5]


@pytest.fixture
def forbid_heavy_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail loudly if re-embed reaches for the PDF or the metadata model."""

    async def no_parse(*args, **kwargs):
        raise AssertionError("reembed_book must not parse the PDF")

    async def no_metadata(*args, **kwargs):
        raise AssertionError("reembed_book must not call the metadata model")

    monkeypatch.setattr(parser_module, "parse_pdf", no_parse)
    monkeypatch.setattr(metadata_module, "extract_metadata_batch", no_metadata)


def _seed(session) -> tuple[Book, Section, Section]:
    book = Book(title="T", author="A", storage_url="https://example.test/b.pdf")
    session.add(book)
    session.flush()

    part = Section(
        book_id=book.id,
        chapter_index=0,
        section_index=None,
        level=0,
        heading="Part One",
        page_start=1,
        page_end=1,
        word_count=40,
        is_connective=False,
        raw_text="opening text of the part",
        section_metadata={"summary": "Part summary.", "concepts": ["alpha"]},
        embedding=[0.0],
        embed_version=1,
    )
    session.add(part)
    session.flush()

    chapter = Section(
        book_id=book.id,
        chapter_index=0,
        section_index=0,
        level=1,
        heading="Chapter Two",
        page_start=2,
        page_end=3,
        word_count=40,
        is_connective=False,
        raw_text="opening text of the chapter",
        section_metadata={"summary": "Chapter summary.", "concepts": ["beta"]},
        embedding=[0.0],
        embed_version=1,
        parent_section_id=part.id,
    )
    session.add(chapter)
    session.flush()

    session.add(
        Chunk(
            section_id=chapter.id,
            chunk_index=0,
            content="chunk body text",
            embedding=[0.0],
            embed_version=1,
        )
    )
    session.flush()
    return book, part, chapter


async def test_reembed_updates_sections_and_chunks(session, forbid_heavy_paths) -> None:
    book, _part, _chapter = _seed(session)

    stats = await reembed_book(session, book.id, embedder=_Recorder())

    assert stats == {"sections": 2, "chunks": 1}
    assert all(
        section.embed_version == 2 for section in session.scalars(select(Section))
    )
    assert all(
        chunk.embed_version == 2 for chunk in session.scalars(select(Chunk))
    )


async def test_reembed_uses_the_prefixed_breadcrumb_inputs(
    session, forbid_heavy_paths
) -> None:
    book, _part, _chapter = _seed(session)
    recorder = _Recorder()

    await reembed_book(session, book.id, embedder=recorder)

    assert all(text.startswith("search_document: ") for text in recorder.inputs)
    assert any(
        text.startswith("search_document: Part One > Chapter Two\n") for text in recorder.inputs
    ), recorder.inputs
    # The section input carries its stored summary and concepts.
    assert any("Chapter summary." in text for text in recorder.inputs)
    assert any("Concepts: beta" in text for text in recorder.inputs)


async def test_reembed_does_not_invent_chunk_pages(session, forbid_heavy_paths) -> None:
    book, _part, _chapter = _seed(session)

    await reembed_book(session, book.id, embedder=_Recorder())

    chunk = session.scalars(select(Chunk)).one()
    assert chunk.page_start is None
    assert chunk.page_end is None


async def test_reembed_leaves_a_parentless_section_with_a_bare_heading(
    session, forbid_heavy_paths
) -> None:
    book, _part, _chapter = _seed(session)
    recorder = _Recorder()

    await reembed_book(session, book.id, embedder=recorder)

    # "Part One" has no parent, so its breadcrumb is just its own heading.
    assert any(
        text.startswith("search_document: Part One\n") for text in recorder.inputs
    ), recorder.inputs


async def test_reembed_on_a_book_with_no_sections_is_a_no_op(
    session, forbid_heavy_paths
) -> None:
    book = Book(title="Empty", author="A", storage_url="https://example.test/e.pdf")
    session.add(book)
    session.flush()

    stats = await reembed_book(session, book.id, embedder=_Recorder())

    assert stats == {"sections": 0, "chunks": 0}


async def test_reembed_module_imports_no_parser_or_metadata_helper() -> None:
    """A structural guard: the worker must not even import those modules."""
    from app.workers import reembed

    source = __import__("inspect").getsource(reembed)
    assert "from app.pipeline.parser" not in source
    assert "from app.pipeline.metadata" not in source
