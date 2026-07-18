"""CoverageEvent ORM model.

Coverage events are the append-only log that drives the coverage
scoring system. Every user interaction that touches a section emits
one event row. Scores are derived by aggregating events — never
stored as a mutable field.

Event types and point values (defined in core/config.py):
  page_viewed       → 1pt
  note_matched      → 3pt
  notes_generated   → 4pt
  qa_asked          → 5pt
  quiz_answered     → 5pt

Coverage score = sum of points per (user_id, section_id), capped at 15.
Visual states: 0=uncovered, 1–4=mentioned, 5–9=partial, 10–15=well covered.
"""

import datetime
import enum
import uuid
from typing import Any, Optional

import sqlalchemy as sa
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import JSONB, Base


class EventType(str, enum.Enum):
    """All interaction types that contribute to coverage scoring."""

    PAGE_VIEWED = "page_viewed"
    NOTE_MATCHED = "note_matched"
    NOTES_GENERATED = "notes_generated"
    QA_ASKED = "qa_asked"
    QUIZ_ANSWERED = "quiz_answered"


class CoverageEvent(Base):
    """Append-only event log — never updated or deleted.

    Does NOT include TimestampMixin because coverage events have no
    meaningful `updated_at` — they are write-once records.
    """

    __tablename__ = "coverage_event"

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
    section_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    event_type: Mapped[EventType] = mapped_column(
        SAEnum(
            EventType,
            name="event_type",
            values_callable=lambda obj: [e.value for e in obj],
        ),
        nullable=False,
        index=True,
    )
    event_metadata: Mapped[Optional[dict[str, Any]]] = mapped_column(
        "event_metadata",
        JSONB,
        nullable=True,
        comment="Flexible payload: e.g. {note_session_id, score_before, page_number}",
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        sa.DateTime(timezone=False),
        server_default=sa.func.now(),
        nullable=False,
        index=True,
        comment=(
            "Postgres-assigned timestamp (server_default). Never updated — "
            "coverage events are append-only."
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<CoverageEvent id={self.id} user={self.user_id} "
            f"section={self.section_id} type={self.event_type}>"
        )
