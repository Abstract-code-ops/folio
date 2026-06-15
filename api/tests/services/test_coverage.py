"""Tests for the Coverage service layer.

Uses async SQLite in-memory database via the ``async_session`` fixture.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.book import Book, IngestionStatus
from app.models.coverage_event import CoverageEvent, EventType
from app.models.section import Section
from app.services.coverage import (
    CoverageMapResponse,
    SectionCoverage,
    coverage_state_from_score,
    get_coverage_map,
)


class TestCoverageStateDerivation:
    """coverage_state_from_score() helper."""

    def test_uncovered(self):
        assert coverage_state_from_score(0) == "uncovered"

    def test_mentioned_low(self):
        assert coverage_state_from_score(1) == "mentioned"

    def test_mentioned_high(self):
        assert coverage_state_from_score(4) == "mentioned"

    def test_partial_low(self):
        assert coverage_state_from_score(5) == "partial"

    def test_partial_high(self):
        assert coverage_state_from_score(9) == "partial"

    def test_well_covered_low(self):
        assert coverage_state_from_score(10) == "well_covered"

    def test_well_covered_high(self):
        assert coverage_state_from_score(15) == "well_covered"

    def test_above_cap(self):
        # Cap is 15, but function handles raw values above cap gracefully
        assert coverage_state_from_score(20) == "well_covered"


class TestGetCoverageMap:
    """get_coverage_map() service function."""

    @pytest.mark.asyncio
    async def test_no_sections(self, async_session: AsyncSession):
        """A book with no sections returns an empty map."""
        book = Book(title="Empty", author="A", storage_url="url")
        async_session.add(book)
        await async_session.commit()

        user_id = uuid.uuid4()
        result = await get_coverage_map(async_session, user_id, book.id)

        assert isinstance(result, CoverageMapResponse)
        assert result.book_id == book.id
        assert result.sections == []

    @pytest.mark.asyncio
    async def test_all_sections_uncovered(self, async_session: AsyncSession):
        """Sections with no events have score 0 / uncovered."""
        book = Book(title="Test Book", author="A", storage_url="url")
        async_session.add(book)
        await async_session.flush()

        sections = [
            Section(
                book_id=book.id,
                chapter_index=0,
                section_index=0,
                level=0,
                heading="Chapter 1",
                page_start=1,
                page_end=10,
                word_count=500,
            ),
            Section(
                book_id=book.id,
                chapter_index=0,
                section_index=1,
                level=1,
                heading="Section 1.1",
                page_start=2,
                page_end=5,
                word_count=200,
            ),
        ]
        async_session.add_all(sections)
        await async_session.commit()

        user_id = uuid.uuid4()
        result = await get_coverage_map(async_session, user_id, book.id)

        assert len(result.sections) == 2
        for sec in result.sections:
            assert sec.coverage_score == 0
            assert sec.coverage_state == "uncovered"

    @pytest.mark.asyncio
    async def test_score_aggregation(self, async_session: AsyncSession):
        """Events are summed per section using the point values from config.

        PAGE_VIEWED=1pt, NOTE_MATCHED=3pt → total=4 → "mentioned".
        """
        book = Book(title="Scored", author="A", storage_url="url")
        async_session.add(book)
        await async_session.flush()

        section = Section(
            book_id=book.id,
            chapter_index=0,
            section_index=0,
            level=0,
            heading="Ch 1",
            page_start=1,
            page_end=10,
            word_count=500,
        )
        async_session.add(section)
        await async_session.flush()

        user_id = uuid.uuid4()

        # Two events: PAGE_VIEWED (1pt) + NOTE_MATCHED (3pt) = 4pt → "mentioned"
        events = [
            CoverageEvent(
                user_id=user_id,
                book_id=book.id,
                section_id=section.id,
                event_type=EventType.PAGE_VIEWED,
            ),
            CoverageEvent(
                user_id=user_id,
                book_id=book.id,
                section_id=section.id,
                event_type=EventType.NOTE_MATCHED,
            ),
        ]
        async_session.add_all(events)
        await async_session.commit()

        result = await get_coverage_map(async_session, user_id, book.id)

        assert len(result.sections) == 1
        assert result.sections[0].coverage_score == 4
        assert result.sections[0].coverage_state == "mentioned"

    @pytest.mark.asyncio
    async def test_score_capped_at_15(self, async_session: AsyncSession):
        """Score never exceeds the cap, even with many events."""
        book = Book(title="Capped", author="A", storage_url="url")
        async_session.add(book)
        await async_session.flush()

        section = Section(
            book_id=book.id,
            chapter_index=0,
            section_index=0,
            level=0,
            heading="Ch 1",
            page_start=1,
            page_end=10,
            word_count=500,
        )
        async_session.add(section)
        await async_session.flush()

        user_id = uuid.uuid4()

        # 4 QA_ASKED events × 5pt = 20, should cap at 15
        events = [
            CoverageEvent(
                user_id=user_id,
                book_id=book.id,
                section_id=section.id,
                event_type=EventType.QA_ASKED,
            )
            for _ in range(4)
        ]
        async_session.add_all(events)
        await async_session.commit()

        result = await get_coverage_map(async_session, user_id, book.id)

        assert result.sections[0].coverage_score == 15
        assert result.sections[0].coverage_state == "well_covered"

    @pytest.mark.asyncio
    async def test_multiple_sections_different_scores(
        self, async_session: AsyncSession,
    ):
        """Different sections get independent scores."""
        book = Book(title="Multi", author="A", storage_url="url")
        async_session.add(book)
        await async_session.flush()

        sec_a = Section(
            book_id=book.id, chapter_index=0, section_index=0,
            level=0, heading="Ch 1", page_start=1, page_end=5, word_count=300,
        )
        sec_b = Section(
            book_id=book.id, chapter_index=1, section_index=0,
            level=0, heading="Ch 2", page_start=6, page_end=10, word_count=400,
        )
        async_session.add_all([sec_a, sec_b])
        await async_session.flush()

        user_id = uuid.uuid4()

        # sec_a: 3 PAGE_VIEWED = 3pt → "mentioned"
        # sec_b: 2 NOTE_MATCHED + 1 QA_ASKED = 3+3+5=11pt → "well_covered"
        events = [
            CoverageEvent(
                user_id=user_id, book_id=book.id,
                section_id=sec_a.id, event_type=EventType.PAGE_VIEWED,
            ),
            CoverageEvent(
                user_id=user_id, book_id=book.id,
                section_id=sec_a.id, event_type=EventType.PAGE_VIEWED,
            ),
            CoverageEvent(
                user_id=user_id, book_id=book.id,
                section_id=sec_a.id, event_type=EventType.PAGE_VIEWED,
            ),
            CoverageEvent(
                user_id=user_id, book_id=book.id,
                section_id=sec_b.id, event_type=EventType.NOTE_MATCHED,
            ),
            CoverageEvent(
                user_id=user_id, book_id=book.id,
                section_id=sec_b.id, event_type=EventType.NOTE_MATCHED,
            ),
            CoverageEvent(
                user_id=user_id, book_id=book.id,
                section_id=sec_b.id, event_type=EventType.QA_ASKED,
            ),
        ]
        async_session.add_all(events)
        await async_session.commit()

        result = await get_coverage_map(async_session, user_id, book.id)

        sections_by_id = {s.id: s for s in result.sections}

        assert sections_by_id[sec_a.id].coverage_score == 3
        assert sections_by_id[sec_a.id].coverage_state == "mentioned"

        assert sections_by_id[sec_b.id].coverage_score == 11
        assert sections_by_id[sec_b.id].coverage_state == "well_covered"

    @pytest.mark.asyncio
    async def test_connective_section_preserved(
        self, async_session: AsyncSession,
    ):
        """Connective sections are returned with their is_connective flag."""
        book = Book(title="Connective", author="A", storage_url="url")
        async_session.add(book)
        await async_session.flush()

        section = Section(
            book_id=book.id,
            chapter_index=0,
            section_index=0,
            level=0,
            heading="Transition",
            page_start=1,
            page_end=2,
            word_count=120,
            is_connective=True,
        )
        async_session.add(section)
        await async_session.commit()

        user_id = uuid.uuid4()
        result = await get_coverage_map(async_session, user_id, book.id)

        assert result.sections[0].is_connective is True
        assert result.sections[0].word_count == 120

    @pytest.mark.asyncio
    async def test_key_terms_from_metadata(
        self, async_session: AsyncSession,
    ):
        """Key terms are extracted from section_metadata when available."""
        book = Book(title="Metadata", author="A", storage_url="url")
        async_session.add(book)
        await async_session.flush()

        section = Section(
            book_id=book.id,
            chapter_index=0,
            section_index=0,
            level=0,
            heading="Ch with Concepts",
            page_start=1,
            page_end=10,
            word_count=500,
            section_metadata={
                "concepts": ["photosynthesis", "chlorophyll", "light reaction"],
                "summary": "A chapter about photosynthesis",
            },
        )
        async_session.add(section)
        await async_session.commit()

        user_id = uuid.uuid4()
        result = await get_coverage_map(async_session, user_id, book.id)

        assert result.sections[0].key_terms == [
            "photosynthesis", "chlorophyll", "light reaction",
        ]

    @pytest.mark.asyncio
    async def test_empty_key_terms_when_no_metadata(
        self, async_session: AsyncSession,
    ):
        """Sections without metadata get an empty key_terms list."""
        book = Book(title="No Meta", author="A", storage_url="url")
        async_session.add(book)
        await async_session.flush()

        section = Section(
            book_id=book.id,
            chapter_index=0,
            section_index=0,
            level=0,
            heading="Ch 1",
            page_start=1,
            page_end=10,
            word_count=500,
        )
        async_session.add(section)
        await async_session.commit()

        user_id = uuid.uuid4()
        result = await get_coverage_map(async_session, user_id, book.id)

        assert result.sections[0].key_terms == []

    @pytest.mark.asyncio
    async def test_user_scoped(
        self, async_session: AsyncSession,
    ):
        """Events from one user do not leak into another user's map."""
        book = Book(title="Scoped", author="A", storage_url="url")
        async_session.add(book)
        await async_session.flush()

        section = Section(
            book_id=book.id,
            chapter_index=0,
            section_index=0,
            level=0,
            heading="Ch 1",
            page_start=1,
            page_end=10,
            word_count=500,
        )
        async_session.add(section)
        await async_session.flush()

        user_a = uuid.uuid4()
        user_b = uuid.uuid4()

        # Only user_a has events
        async_session.add(
            CoverageEvent(
                user_id=user_a,
                book_id=book.id,
                section_id=section.id,
                event_type=EventType.QA_ASKED,
            )
        )
        await async_session.commit()

        result_a = await get_coverage_map(async_session, user_a, book.id)
        result_b = await get_coverage_map(async_session, user_b, book.id)

        assert result_a.sections[0].coverage_score == 5
        assert result_b.sections[0].coverage_score == 0

    @pytest.mark.asyncio
    async def test_response_shape(self, async_session: AsyncSession):
        """Verify the full response structure matches the schema."""
        book = Book(title="Shape", author="A", storage_url="url")
        async_session.add(book)
        await async_session.flush()

        section = Section(
            book_id=book.id,
            chapter_index=0,
            section_index=0,
            level=0,
            heading="Ch 1",
            page_start=1,
            page_end=5,
            word_count=300,
        )
        async_session.add(section)
        await async_session.commit()

        user_id = uuid.uuid4()
        result = await get_coverage_map(async_session, user_id, book.id)

        # Top-level shape
        assert isinstance(result, CoverageMapResponse)
        assert isinstance(result.book_id, uuid.UUID)
        assert isinstance(result.sections, list)

        # Section shape
        sec = result.sections[0]
        assert isinstance(sec, SectionCoverage)
        assert isinstance(sec.id, uuid.UUID)
        assert isinstance(sec.heading, str)
        assert isinstance(sec.page_start, int)
        assert isinstance(sec.page_end, int)
        assert isinstance(sec.word_count, int)
        assert isinstance(sec.is_connective, bool)
        assert isinstance(sec.coverage_score, int)
        assert isinstance(sec.coverage_state, str)
        assert isinstance(sec.key_terms, list)
