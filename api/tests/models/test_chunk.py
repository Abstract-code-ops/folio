"""Tests for the Chunk ORM model."""

import pytest
from sqlalchemy import select

from app.models.book import Book
from app.models.chunk import Chunk
from app.models.section import Section


@pytest.fixture
def book(session):
    b = Book(
        title="Chunk Test Book",
        author="Author",
        storage_url="https://storage.example.com/book.pdf",
    )
    session.add(b)
    session.commit()
    return b


@pytest.fixture
def section(session, book):
    s = Section(
        book_id=book.id,
        chapter_index=0,
        level=0,
        heading="Ch 1",
        page_start=1,
        page_end=10,
        word_count=2000,
    )
    session.add(s)
    session.commit()
    return s


class TestChunkCreate:
    """Chunk instantiation and defaults."""

    def test_create_chunk(self, session, section):
        chunk = Chunk(
            section_id=section.id,
            chunk_index=0,
            content="This is the first chunk of the section.",
        )
        session.add(chunk)
        session.commit()

        assert chunk.id is not None
        assert chunk.chunk_index == 0
        assert chunk.content == "This is the first chunk of the section."
        assert chunk.embedding is None

    def test_multiple_chunks_ordered(self, session, section):
        chunks = [
            Chunk(
                section_id=section.id,
                chunk_index=i,
                content=f"Chunk number {i}",
            )
            for i in range(5)
        ]
        session.add_all(chunks)
        session.commit()

        result = session.execute(
            select(Chunk)
            .where(Chunk.section_id == section.id)
            .order_by(Chunk.chunk_index)
        ).scalars().all()

        assert len(result) == 5
        for i, c in enumerate(result):
            assert c.chunk_index == i
            assert c.content == f"Chunk number {i}"


class TestChunkRelationships:
    """Section → Chunk relationship."""

    def test_section_chunks_relationship(self, session, section):
        chunks = [
            Chunk(section_id=section.id, chunk_index=i, content=f"c{i}")
            for i in range(3)
        ]
        session.add_all(chunks)
        session.commit()
        session.refresh(section)

        assert len(section.chunks) == 3

    def test_chunk_belongs_to_section(self, session, section):
        chunk = Chunk(
            section_id=section.id,
            chunk_index=0,
            content="Belongs to section.",
        )
        session.add(chunk)
        session.commit()

        assert chunk.section.id == section.id
