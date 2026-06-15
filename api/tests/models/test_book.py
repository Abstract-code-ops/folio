"""Tests for the Book ORM model."""

import pytest
from sqlalchemy import select

from app.models.book import Book, IngestionStatus


class TestBookCreate:
    """Book instantiation and default values."""

    def test_create_minimal(self, session):
        book = Book(
            title="Test Book",
            author="Test Author",
            storage_url="https://storage.example.com/book.pdf",
        )
        session.add(book)
        session.commit()

        assert book.id is not None
        assert book.title == "Test Book"
        assert book.author == "Test Author"
        assert book.storage_url == "https://storage.example.com/book.pdf"
        assert book.ingestion_status == IngestionStatus.NOT_STARTED
        assert book.created_at is not None
        assert book.updated_at is None
        assert book.section_count is None
        assert book.word_count is None

    def test_create_full(self, session):
        book = Book(
            title="Full Book",
            author="Author Name",
            description="A comprehensive test book.",
            cover_image_url="https://storage.example.com/cover.jpg",
            storage_url="https://storage.example.com/book.pdf",
            section_count=10,
            word_count=50000,
        )
        session.add(book)
        session.commit()

        assert book.description == "A comprehensive test book."
        assert book.cover_image_url == "https://storage.example.com/cover.jpg"
        assert book.section_count == 10
        assert book.word_count == 50000


class TestBookStatus:
    """Ingestion status transitions."""

    def test_default_status(self, session):
        book = Book(
            title="Default Status",
            author="Author",
            storage_url="https://storage.example.com/book.pdf",
        )
        session.add(book)
        session.flush()
        assert book.ingestion_status == IngestionStatus.NOT_STARTED

    def test_set_status_processing(self, session):
        book = Book(
            title="Processing Book",
            author="Author",
            storage_url="https://storage.example.com/book.pdf",
            ingestion_status=IngestionStatus.PROCESSING,
        )
        session.add(book)
        session.commit()
        assert book.ingestion_status == IngestionStatus.PROCESSING

    def test_set_status_completed(self, session):
        book = Book(
            title="Completed Book",
            author="Author",
            storage_url="https://storage.example.com/book.pdf",
            ingestion_status=IngestionStatus.COMPLETED,
        )
        session.add(book)
        session.commit()
        assert book.ingestion_status == IngestionStatus.COMPLETED

    def test_set_status_failed(self, session):
        book = Book(
            title="Failed Book",
            author="Author",
            storage_url="https://storage.example.com/book.pdf",
            ingestion_status=IngestionStatus.FAILED,
        )
        session.add(book)
        session.commit()
        assert book.ingestion_status == IngestionStatus.FAILED


class TestBookQuery:
    """Querying books."""

    def test_query_by_title(self, session):
        book = Book(
            title="Query Me",
            author="Author",
            storage_url="https://storage.example.com/book.pdf",
        )
        session.add(book)
        session.commit()

        result = session.execute(
            select(Book).where(Book.title == "Query Me")
        ).scalar_one()
        assert result.id == book.id

    def test_query_by_status(self, session):
        book = Book(
            title="Status Query",
            author="Author",
            storage_url="https://storage.example.com/book.pdf",
            ingestion_status=IngestionStatus.PROCESSING,
        )
        session.add(book)
        session.commit()

        result = session.execute(
            select(Book).where(Book.ingestion_status == IngestionStatus.PROCESSING)
        ).scalars().all()
        assert len(result) >= 1

    def test_query_empty_list(self, session):
        result = session.execute(select(Book)).scalars().all()
        assert len(result) == 0


class TestBookRepr:
    """String representation."""

    def test_repr(self, session):
        book = Book(
            title="Repr Book",
            author="Author",
            storage_url="https://storage.example.com/book.pdf",
        )
        session.add(book)
        session.flush()
        rep = repr(book)
        assert "Repr Book" in rep
        assert "NOT_STARTED" in rep
        assert "Book" in rep
