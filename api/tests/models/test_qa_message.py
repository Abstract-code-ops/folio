"""Tests for the QAMessage ORM model."""

import uuid

from sqlalchemy import select

from app.models.qa_message import QAMessage


class TestQAMessageCreate:
    """QAMessage instantiation."""

    def test_create_message(self, session):
        msg = QAMessage(
            user_id=uuid.uuid4(),
            book_id=uuid.uuid4(),
            section_id=uuid.uuid4(),
            question="What is photosynthesis?",
            answer="Photosynthesis is the process by which plants convert light into energy.",
        )
        session.add(msg)
        session.commit()

        assert msg.id is not None
        assert msg.question == "What is photosynthesis?"
        assert "Photosynthesis is the process" in msg.answer
        assert msg.sources is None

    def test_create_with_sources(self, session):
        sources = [
            {
                "section_heading": "Photosynthesis Overview",
                "page_start": 42,
                "page_end": 45,
                "excerpt": "Plants use sunlight to synthesize foods.",
            },
        ]
        msg = QAMessage(
            user_id=uuid.uuid4(),
            book_id=uuid.uuid4(),
            section_id=uuid.uuid4(),
            question="How do plants make food?",
            answer="Through photosynthesis.",
            sources=sources,
        )
        session.add(msg)
        session.commit()

        assert msg.sources is not None
        assert len(msg.sources) == 1
        assert msg.sources[0]["section_heading"] == "Photosynthesis Overview"
        assert msg.sources[0]["page_start"] == 42


class TestQAMessageQuery:
    """Querying messages by user and section."""

    def test_messages_by_section(self, session):
        user_id = uuid.uuid4()
        section_id = uuid.uuid4()

        msgs = [
            QAMessage(
                user_id=user_id,
                book_id=uuid.uuid4(),
                section_id=section_id,
                question=f"Question {i}",
                answer=f"Answer {i}",
            )
            for i in range(3)
        ]
        session.add_all(msgs)
        session.commit()

        result = session.execute(
            select(QAMessage)
            .where(QAMessage.section_id == section_id)
            .order_by(QAMessage.created_at)
        ).scalars().all()
        assert len(result) == 3

    def test_messages_by_user(self, session):
        user_id = uuid.uuid4()

        msgs = [
            QAMessage(
                user_id=user_id,
                book_id=uuid.uuid4(),
                section_id=uuid.uuid4(),
                question=f"Q {i}",
                answer=f"A {i}",
            )
            for i in range(2)
        ]
        session.add_all(msgs)
        session.commit()

        result = session.execute(
            select(QAMessage).where(QAMessage.user_id == user_id)
        ).scalars().all()
        assert len(result) == 2
