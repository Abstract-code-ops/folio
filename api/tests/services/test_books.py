"""Tests for the Book service layer.

Uses async SQLite in-memory database via the ``async_session`` fixture.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.book import Book, IngestionStatus
from app.services.books import BookResponse, BookListResponse, get_book, list_books


class TestListBooks:
    """list_books() service function."""

    @pytest.mark.asyncio
    async def test_empty_library(self, async_session: AsyncSession):
        result = await list_books(async_session)
        assert isinstance(result, BookListResponse)
        assert result.books == []
        assert result.total == 0

    @pytest.mark.asyncio
    async def test_list_all_books(self, async_session: AsyncSession):
        books = [
            Book(title="A Book", author="Author A", storage_url="url1"),
            Book(title="B Book", author="Author B", storage_url="url2"),
        ]
        async_session.add_all(books)
        await async_session.commit()

        result = await list_books(async_session)
        assert result.total == 2
        assert result.books[0].title == "A Book"
        assert result.books[1].title == "B Book"

    @pytest.mark.asyncio
    async def test_filter_by_status(self, async_session: AsyncSession):
        books = [
            Book(
                title="Ready", author="A", storage_url="u1",
                ingestion_status=IngestionStatus.COMPLETED,
            ),
            Book(
                title="Pending", author="B", storage_url="u2",
                ingestion_status=IngestionStatus.NOT_STARTED,
            ),
        ]
        async_session.add_all(books)
        await async_session.commit()

        result = await list_books(
            async_session, status=IngestionStatus.COMPLETED,
        )
        assert result.total == 1
        assert result.books[0].title == "Ready"

    @pytest.mark.asyncio
    async def test_pagination(self, async_session: AsyncSession):
        books = [
            Book(title=f"Book {i}", author="A", storage_url=f"u{i}")
            for i in range(5)
        ]
        async_session.add_all(books)
        await async_session.commit()

        result = await list_books(async_session, limit=2, offset=0)
        assert result.total == 5
        assert len(result.books) == 2

        result_page2 = await list_books(async_session, limit=2, offset=2)
        assert len(result_page2.books) == 2


class TestGetBook:
    """get_book() service function."""

    @pytest.mark.asyncio
    async def test_get_existing_book(self, async_session: AsyncSession):
        book = Book(title="Find Me", author="Author", storage_url="url")
        async_session.add(book)
        await async_session.commit()

        found = await get_book(async_session, book.id)
        assert found is not None
        assert isinstance(found, BookResponse)
        assert found.title == "Find Me"
        assert found.author == "Author"

    @pytest.mark.asyncio
    async def test_get_nonexistent_book(self, async_session: AsyncSession):
        found = await get_book(async_session, uuid.uuid4())
        assert found is None

    @pytest.mark.asyncio
    async def test_get_book_response_shape(self, async_session: AsyncSession):
        book = Book(
            title="Shape Test",
            author="Author",
            storage_url="url",
            description="A test book",
            section_count=5,
            word_count=10000,
            ingestion_status=IngestionStatus.COMPLETED,
        )
        async_session.add(book)
        await async_session.commit()

        found = await get_book(async_session, book.id)
        assert found is not None
        assert isinstance(found.id, uuid.UUID)
        assert found.description == "A test book"
        assert found.section_count == 5
        assert found.word_count == 10000
        assert found.ingestion_status == IngestionStatus.COMPLETED
