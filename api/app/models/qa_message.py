"""QAMessage ORM model.

Each row is a single Q&A exchange between a student and the AI tutor.
Questions are scoped to a specific section of a specific book. Every
answer includes source citations (section + page references) stored
as JSONB.

The Q&A history is user-scoped and displayed in the Chat tab of the
left panel, ordered by creation time.
"""

import uuid
from typing import Any, Optional

from sqlalchemy import Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import JSONB, Base, TimestampMixin


class QAMessage(TimestampMixin, Base):
    __tablename__ = "qa_message"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
        comment="User ID from Better Auth",
    )
    book_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    section_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        index=True,
        comment=(
            "The section the question was scoped to; NULL for a turn that did "
            "not retrieve (a greeting or an off-topic decline)"
        ),
    )
    question: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    answer: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    sources: Mapped[Optional[list[dict[str, Any]]]] = mapped_column(
        JSONB,
        nullable=True,
        comment=(
            "Source citations for the answer: "
            "[{section_heading, page_start, page_end, excerpt}, ...]. "
            "Populated by the Q&A pipeline."
        ),
    )
    diagnostics: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=True,
        comment=(
            "What happened during the turn, for the eval page: agent action, "
            "search queries, retrieved passages with distances, citations "
            "emitted and any stream error. NULL for turns recorded before it "
            "existed."
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<QAMessage id={self.id} user={self.user_id} "
            f"section={self.section_id}>"
        )
