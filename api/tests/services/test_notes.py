"""Tests for the Note Session service layer.

Uses async SQLite in-memory database via the ``async_session`` fixture.
The Dramatiq ``.send()`` call is mocked to avoid needing a real broker.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.note_session import NoteSession, NoteSessionStatus, NoteSource
from app.services.notes import (
    NoteSessionListResponse,
    NoteSessionResponse,
    create_note_session,
    list_note_sessions,
)


class TestCreateNoteSession:
    """create_note_session() service function."""

    @pytest.mark.asyncio
    async def test_create_pasted_session(
        self, async_session: AsyncSession,
    ):
        """A pasted note session is created with PENDING status."""
        user_id = uuid.uuid4()
        book_id = uuid.uuid4()
        raw_text = "These are my lecture notes on photosynthesis."

        with patch(
            "app.workers.note_session.process_note_session.send",
            autospec=True,
        ) as mock_send:
            mock_send.return_value.message_id = "mock-job-123"

            result = await create_note_session(
                async_session,
                user_id=user_id,
                book_id=book_id,
                raw_text=raw_text,
                source=NoteSource.PASTED,
            )

        assert isinstance(result, NoteSessionResponse)
        assert result.source == NoteSource.PASTED
        assert result.status == NoteSessionStatus.PENDING
        assert result.matched_section_count is None
        assert result.job_id == "mock-job-123"
        assert result.book_id == book_id

        # Verify the session was persisted
        db_session = await async_session.get(NoteSession, result.id)
        assert db_session is not None
        assert db_session.raw_text == raw_text
        assert db_session.status == NoteSessionStatus.PENDING

    @pytest.mark.asyncio
    async def test_create_ai_generated_session(
        self, async_session: AsyncSession,
    ):
        """AI-generated sessions are created with AI_GENERATED source."""
        user_id = uuid.uuid4()
        book_id = uuid.uuid4()

        with patch(
            "app.workers.note_session.process_note_session.send",
            autospec=True,
        ) as mock_send:
            mock_send.return_value.message_id = "mock-job-456"

            result = await create_note_session(
                async_session,
                user_id=user_id,
                book_id=book_id,
                raw_text="AI-generated notes for chapter 1.",
                source=NoteSource.AI_GENERATED,
                title="Chapter 1 Summary",
            )

        assert result.source == NoteSource.AI_GENERATED
        assert result.title == "Chapter 1 Summary"
        assert result.job_id == "mock-job-456"

    @pytest.mark.asyncio
    async def test_enqueues_job_with_session_id(
        self, async_session: AsyncSession,
    ):
        """The Dramatiq job is enqueued with the correct session ID."""
        user_id = uuid.uuid4()
        book_id = uuid.uuid4()

        with patch(
            "app.workers.note_session.process_note_session.send",
            autospec=True,
        ) as mock_send:
            mock_send.return_value.message_id = "mock-job-789"

            result = await create_note_session(
                async_session,
                user_id=user_id,
                book_id=book_id,
                raw_text="Test notes.",
                source=NoteSource.PASTED,
            )

        # The send() call should have been made with the session ID
        mock_send.assert_called_once()
        call_arg = mock_send.call_args[0][0]
        assert call_arg == str(result.id)

    @pytest.mark.asyncio
    async def test_user_scoped(
        self, async_session: AsyncSession,
    ):
        """The session is correctly scoped to the creating user."""
        user_id = uuid.uuid4()
        book_id = uuid.uuid4()

        with patch(
            "app.workers.note_session.process_note_session.send",
            autospec=True,
        ) as mock_send:
            mock_send.return_value.message_id = "mock-job"

            result = await create_note_session(
                async_session,
                user_id=user_id,
                book_id=book_id,
                raw_text="User scoped notes.",
                source=NoteSource.PASTED,
            )

        assert result.book_id == book_id

        # Verify in DB
        db_session = await async_session.get(NoteSession, result.id)
        assert db_session is not None
        assert db_session.user_id == user_id
        assert db_session.book_id == book_id

    @pytest.mark.asyncio
    async def test_response_shape(
        self, async_session: AsyncSession,
    ):
        """Verify the full response structure matches the schema."""
        user_id = uuid.uuid4()
        book_id = uuid.uuid4()

        with patch(
            "app.workers.note_session.process_note_session.send",
            autospec=True,
        ) as mock_send:
            mock_send.return_value.message_id = "mock-job"

            result = await create_note_session(
                async_session,
                user_id=user_id,
                book_id=book_id,
                raw_text="Shape check.",
                source=NoteSource.PASTED,
            )

        assert isinstance(result.id, uuid.UUID)
        assert isinstance(result.book_id, uuid.UUID)
        assert isinstance(result.status, NoteSessionStatus)
        assert isinstance(result.source, NoteSource)
        assert isinstance(result.job_id, str)


class TestListNoteSessions:
    """list_note_sessions() -- the read path behind GET /notes."""

    @staticmethod
    def _stored_session(
        *,
        user_id: uuid.UUID,
        book_id: uuid.UUID,
        created_at: datetime,
        title: str,
    ) -> NoteSession:
        """A session as the similarity worker would leave it: completed, no job."""
        return NoteSession(
            user_id=user_id,
            book_id=book_id,
            raw_text="Notes on the section.",
            source=NoteSource.PASTED,
            title=title,
            status=NoteSessionStatus.COMPLETED,
            matched_section_count=3,
            created_at=created_at,
        )

    @pytest.mark.asyncio
    async def test_empty_book_returns_no_sessions(
        self, async_session: AsyncSession,
    ):
        """An untouched book lists nothing rather than raising."""
        result = await list_note_sessions(
            async_session,
            user_id=uuid.uuid4(),
            book_id=uuid.uuid4(),
        )

        assert isinstance(result, NoteSessionListResponse)
        assert result.sessions == []
        assert result.total == 0

    @pytest.mark.asyncio
    async def test_stored_session_is_returned_without_a_job_id(
        self, async_session: AsyncSession,
    ):
        """Regression: a stored session has no job_id, and requiring one raised.

        NoteSessionResponse.job_id was a required field, so validating stored
        rows raised and ``GET /notes`` returned 500 for every book.
        """
        user_id = uuid.uuid4()
        book_id = uuid.uuid4()
        async_session.add(
            self._stored_session(
                user_id=user_id,
                book_id=book_id,
                created_at=datetime(2026, 1, 1, 10, 0),
                title="First pass",
            )
        )
        await async_session.flush()

        result = await list_note_sessions(
            async_session, user_id=user_id, book_id=book_id,
        )

        assert result.total == 1
        assert result.sessions[0].job_id is None
        assert result.sessions[0].title == "First pass"
        assert result.sessions[0].matched_section_count == 3

    @pytest.mark.asyncio
    async def test_most_recent_first(
        self, async_session: AsyncSession,
    ):
        """The newest session is listed first, as the UI expects."""
        user_id = uuid.uuid4()
        book_id = uuid.uuid4()
        async_session.add_all([
            self._stored_session(
                user_id=user_id,
                book_id=book_id,
                created_at=datetime(2026, 1, 1, 10, 0),
                title="earlier",
            ),
            self._stored_session(
                user_id=user_id,
                book_id=book_id,
                created_at=datetime(2026, 1, 2, 10, 0),
                title="later",
            ),
        ])
        await async_session.flush()

        result = await list_note_sessions(
            async_session, user_id=user_id, book_id=book_id,
        )

        assert [session.title for session in result.sessions] == ["later", "earlier"]

    @pytest.mark.asyncio
    async def test_scoped_to_the_caller(
        self, async_session: AsyncSession,
    ):
        """Another user's sessions, and another book's, are never listed."""
        user_id = uuid.uuid4()
        other_user_id = uuid.uuid4()
        book_id = uuid.uuid4()
        other_book_id = uuid.uuid4()
        async_session.add_all([
            self._stored_session(
                user_id=user_id,
                book_id=book_id,
                created_at=datetime(2026, 1, 1, 10, 0),
                title="mine",
            ),
            self._stored_session(
                user_id=other_user_id,
                book_id=book_id,
                created_at=datetime(2026, 1, 2, 10, 0),
                title="someone else's",
            ),
            self._stored_session(
                user_id=user_id,
                book_id=other_book_id,
                created_at=datetime(2026, 1, 3, 10, 0),
                title="another book",
            ),
        ])
        await async_session.flush()

        result = await list_note_sessions(
            async_session, user_id=user_id, book_id=book_id,
        )

        assert result.total == 1
        assert [session.title for session in result.sessions] == ["mine"]
