"""NoteSession ORM model.

A note session is a single submission of lecture notes (pasted or typed
by the student, or AI-generated for a chapter range). Each session is
user-scoped and linked to a book. When submitted, a background job runs
the similarity pass against the book's sections and emits
`note_matched` coverage events for sections above the similarity
threshold.

Multiple sessions accumulate into the same coverage map — the map is
per-book, not per-session.
"""

import enum
import uuid
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Enum as SAEnum
from sqlalchemy import Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.book import Book


class NoteSource(str, enum.Enum):
    """How the notes were obtained."""

    PASTED = "pasted"
    AI_GENERATED = "ai_generated"


class NoteSessionStatus(str, enum.Enum):
    """Where the session is in the processing pipeline."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class NoteSession(TimestampMixin, Base):
    __tablename__ = "note_session"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
        comment="User ID from Better Auth (no FK — auth schema is managed externally)",
    )
    book_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
        comment="FK to book.id (no explicit constraint — shared global resource invariant is enforced in service layer)",
    )
    title: Mapped[Optional[str]] = mapped_column(
        String(256),
        nullable=True,
        comment="Optional user-given title for this session",
    )
    source: Mapped[NoteSource] = mapped_column(
        SAEnum(
            NoteSource,
            name="note_source",
        ),
        nullable=False,
    )
    raw_text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Original pasted/typed notes or the generated note text",
    )
    matched_section_count: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Number of sections matched above threshold; populated after similarity pass",
    )
    status: Mapped[NoteSessionStatus] = mapped_column(
        SAEnum(
            NoteSessionStatus,
            name="note_session_status",
        ),
        default=NoteSessionStatus.PENDING,
        nullable=False,
        index=True,
    )

    def __repr__(self) -> str:
        return (
            f"<NoteSession id={self.id} user={self.user_id} "
            f"source={self.source} status={self.status}>"
        )
