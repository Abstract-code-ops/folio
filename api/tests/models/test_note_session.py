"""Tests for the NoteSession ORM model."""

import uuid

from sqlalchemy import select

from app.models.note_session import (
    NoteSession,
    NoteSessionStatus,
    NoteSource,
)


class TestNoteSessionCreate:
    """NoteSession instantiation and defaults."""

    def test_create_pasted(self, session):
        ns = NoteSession(
            user_id=uuid.uuid4(),
            book_id=uuid.uuid4(),
            source=NoteSource.PASTED,
            raw_text="These are my lecture notes.",
        )
        session.add(ns)
        session.commit()

        assert ns.id is not None
        assert ns.source == NoteSource.PASTED
        assert ns.raw_text == "These are my lecture notes."
        assert ns.status == NoteSessionStatus.PENDING
        assert ns.matched_section_count is None

    def test_create_ai_generated(self, session):
        ns = NoteSession(
            user_id=uuid.uuid4(),
            book_id=uuid.uuid4(),
            source=NoteSource.AI_GENERATED,
            raw_text="AI generated notes for chapter 1.",
            title="Chapter 1 Summary",
        )
        session.add(ns)
        session.commit()

        assert ns.source == NoteSource.AI_GENERATED
        assert ns.title == "Chapter 1 Summary"

    def test_default_status(self, session):
        ns = NoteSession(
            user_id=uuid.uuid4(),
            book_id=uuid.uuid4(),
            source=NoteSource.PASTED,
            raw_text="Default status check.",
        )
        session.add(ns)
        session.flush()
        assert ns.status == NoteSessionStatus.PENDING

    def test_status_transitions(self, session):
        ns = NoteSession(
            user_id=uuid.uuid4(),
            book_id=uuid.uuid4(),
            source=NoteSource.PASTED,
            raw_text="Processing test.",
        )
        session.add(ns)
        session.commit()

        ns.status = NoteSessionStatus.PROCESSING
        session.commit()
        assert ns.status == NoteSessionStatus.PROCESSING

        ns.status = NoteSessionStatus.COMPLETED
        ns.matched_section_count = 5
        session.commit()
        assert ns.status == NoteSessionStatus.COMPLETED
        assert ns.matched_section_count == 5


class TestNoteSessionQuery:
    """Querying note sessions by user."""

    def test_sessions_by_user(self, session):
        user_id = uuid.uuid4()
        sessions = [
            NoteSession(
                user_id=user_id,
                book_id=uuid.uuid4(),
                source=NoteSource.PASTED,
                raw_text=f"Session {i}",
            )
            for i in range(3)
        ]
        session.add_all(sessions)
        session.commit()

        result = session.execute(
            select(NoteSession).where(NoteSession.user_id == user_id)
        ).scalars().all()
        assert len(result) == 3
