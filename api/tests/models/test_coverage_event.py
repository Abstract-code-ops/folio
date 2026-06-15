"""Tests for the CoverageEvent ORM model."""

import uuid

from sqlalchemy import func, select

from app.models.coverage_event import CoverageEvent, EventType


class TestCoverageEventCreate:
    """CoverageEvent instantiation and defaults."""

    def test_create_page_viewed(self, session):
        event = CoverageEvent(
            user_id=uuid.uuid4(),
            book_id=uuid.uuid4(),
            section_id=uuid.uuid4(),
            event_type=EventType.PAGE_VIEWED,
        )
        session.add(event)
        session.commit()

        assert event.id is not None
        assert event.event_type == EventType.PAGE_VIEWED
        assert event.created_at is not None
        assert event.event_metadata is None

    def test_create_all_event_types(self, session):
        event_types = list(EventType)
        events = [
            CoverageEvent(
                user_id=uuid.uuid4(),
                book_id=uuid.uuid4(),
                section_id=uuid.uuid4(),
                event_type=et,
            )
            for et in event_types
        ]
        session.add_all(events)
        session.commit()

        for event in events:
            assert event.id is not None

    def test_create_with_metadata(self, session):
        event = CoverageEvent(
            user_id=uuid.uuid4(),
            book_id=uuid.uuid4(),
            section_id=uuid.uuid4(),
            event_type=EventType.NOTE_MATCHED,
            event_metadata={"note_session_id": str(uuid.uuid4()), "score_before": 0},
        )
        session.add(event)
        session.commit()

        assert event.event_metadata is not None
        assert "note_session_id" in event.event_metadata
        assert event.event_metadata["score_before"] == 0


class TestCoverageEventAppendOnly:
    """Coverage events are write-once — verify no updated_at column."""

    def test_no_updated_at_column(self):
        assert not hasattr(CoverageEvent, "updated_at")

    def test_created_at_set_by_server(self, session):
        """created_at uses server_default, but SQLite will set on INSERT."""
        event = CoverageEvent(
            user_id=uuid.uuid4(),
            book_id=uuid.uuid4(),
            section_id=uuid.uuid4(),
            event_type=EventType.QA_ASKED,
        )
        session.add(event)
        session.commit()

        assert event.created_at is not None


class TestCoverageEventQuery:
    """Querying events by user and section."""

    def test_events_by_user(self, session):
        user_id = uuid.uuid4()
        section_id = uuid.uuid4()
        events = [
            CoverageEvent(
                user_id=user_id,
                book_id=uuid.uuid4(),
                section_id=section_id,
                event_type=EventType.PAGE_VIEWED,
            )
            for _ in range(3)
        ]
        session.add_all(events)
        session.commit()

        result = session.execute(
            select(CoverageEvent).where(CoverageEvent.user_id == user_id)
        ).scalars().all()
        assert len(result) == 3

    def test_score_sum(self, session):
        """Each event type has an implicit point value (defined in config.py)."""
        user_id = uuid.uuid4()
        section_id = uuid.uuid4()

        events = [
            CoverageEvent(
                user_id=user_id,
                book_id=uuid.uuid4(),
                section_id=section_id,
                event_type=EventType.PAGE_VIEWED,
            ),
            CoverageEvent(
                user_id=user_id,
                book_id=uuid.uuid4(),
                section_id=section_id,
                event_type=EventType.NOTE_MATCHED,
            ),
            CoverageEvent(
                user_id=user_id,
                book_id=uuid.uuid4(),
                section_id=section_id,
                event_type=EventType.QA_ASKED,
            ),
        ]
        session.add_all(events)
        session.commit()

        count = session.execute(
            select(func.count(CoverageEvent.id))
            .where(
                CoverageEvent.user_id == user_id,
                CoverageEvent.section_id == section_id,
            )
        ).scalar()
        assert count == 3
