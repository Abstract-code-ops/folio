"""Tests for the Section ORM model."""

import pytest
from sqlalchemy import select

from app.models.book import Book, IngestionStatus
from app.models.section import Section


@pytest.fixture
def book(session):
    b = Book(
        title="Section Test Book",
        author="Author",
        storage_url="https://storage.example.com/book.pdf",
    )
    session.add(b)
    session.commit()
    return b


class TestSectionCreate:
    """Section instantiation."""

    def test_create_chapter(self, session, book):
        section = Section(
            book_id=book.id,
            chapter_index=0,
            level=0,
            heading="Chapter 1",
            page_start=1,
            page_end=20,
            word_count=3000,
        )
        session.add(section)
        session.commit()

        assert section.id is not None
        assert section.heading == "Chapter 1"
        assert section.level == 0
        assert section.chapter_index == 0
        assert section.section_index is None
        assert section.is_connective is False
        assert section.parent_section_id is None

    def test_create_subsection(self, session, book):
        parent = Section(
            book_id=book.id,
            chapter_index=0,
            level=0,
            heading="Chapter 1",
            page_start=1,
            page_end=30,
            word_count=5000,
        )
        session.add(parent)
        session.flush()

        child = Section(
            book_id=book.id,
            parent_section_id=parent.id,
            chapter_index=0,
            section_index=0,
            level=1,
            heading="Section 1.1",
            page_start=2,
            page_end=10,
            word_count=1500,
        )
        session.add(child)
        session.commit()

        assert child.parent_section_id == parent.id
        assert child.section_index == 0

    def test_connective_section(self, session, book):
        section = Section(
            book_id=book.id,
            chapter_index=0,
            level=1,
            heading="Short Passage",
            page_start=5,
            page_end=5,
            word_count=120,
            is_connective=True,
        )
        session.add(section)
        session.commit()

        assert section.is_connective is True
        assert section.word_count == 120


class TestSectionRelationships:
    """Book → Section and parent → child relationships."""

    def test_book_sections_relationship(self, session, book):
        s1 = Section(
            book_id=book.id,
            chapter_index=0,
            level=0,
            heading="Ch 1",
            page_start=1,
            page_end=10,
            word_count=1000,
        )
        s2 = Section(
            book_id=book.id,
            chapter_index=1,
            level=0,
            heading="Ch 2",
            page_start=11,
            page_end=20,
            word_count=1000,
        )
        session.add_all([s1, s2])
        session.commit()
        session.refresh(book)

        assert len(book.sections) == 2

    def test_parent_child_relationship(self, session, book):
        parent = Section(
            book_id=book.id,
            chapter_index=0,
            level=0,
            heading="Ch 1",
            page_start=1,
            page_end=20,
            word_count=3000,
        )
        session.add(parent)
        session.flush()

        child = Section(
            book_id=book.id,
            parent_section_id=parent.id,
            chapter_index=0,
            section_index=0,
            level=1,
            heading="S 1.1",
            page_start=2,
            page_end=5,
            word_count=500,
        )
        session.add(child)
        session.commit()
        session.refresh(parent)

        assert len(parent.children) == 1
        assert parent.children[0].id == child.id
        assert child.parent.id == parent.id


class TestSectionQuery:
    """Querying sections by book and hierarchy."""

    def test_sections_by_book(self, session, book):
        sections = [
            Section(
                book_id=book.id,
                chapter_index=i,
                level=0,
                heading=f"Ch {i}",
                page_start=i * 10 + 1,
                page_end=(i + 1) * 10,
                word_count=1000,
            )
            for i in range(3)
        ]
        session.add_all(sections)
        session.commit()

        result = session.execute(
            select(Section).where(Section.book_id == book.id)
            .order_by(Section.chapter_index)
        ).scalars().all()
        assert len(result) == 3
        assert result[0].heading == "Ch 0"

    def test_no_sections_empty_book(self, session, book):
        result = session.execute(
            select(Section).where(Section.book_id == book.id)
        ).scalars().all()
        assert len(result) == 0
