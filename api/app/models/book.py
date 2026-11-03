"""Book ORM model.

Books are a shared global resource — a book record and all its parsed
sections, chunks, and embeddings are created once and shared across
all users. Ingestion runs at most once per book.
"""

import enum
import uuid
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import Enum as SAEnum
from sqlalchemy import Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.section import Section


class IngestionStatus(str, enum.Enum):
    """Tracks where a book is in the ingestion pipeline."""

    NOT_STARTED = "not_started"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class Book(TimestampMixin, Base):
    __tablename__ = "book"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    title: Mapped[str] = mapped_column(
        String(512),
        nullable=False,
        index=True,
    )
    author: Mapped[str] = mapped_column(
        String(256),
        nullable=False,
    )
    category: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        index=True,
        comment="Library category (e.g. Computer Science, Mathematics, ...)",
    )
    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    cover_image_url: Mapped[Optional[str]] = mapped_column(
        String(1024),
        nullable=True,
    )
    storage_url: Mapped[str] = mapped_column(
        String(1024),
        nullable=False,
        comment="Supabase Storage URL for the original PDF",
    )
    ingestion_status: Mapped[IngestionStatus] = mapped_column(
        SAEnum(
            IngestionStatus,
            name="ingestion_status",
            values_callable=lambda obj: [e.value for e in obj],
        ),
        default=IngestionStatus.NOT_STARTED,
        nullable=False,
        index=True,
    )
    section_count: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Total sections found during parsing; populated after ingestion",
    )
    word_count: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Total word count across all sections",
    )

    # ── Relationships ──────────────────────────────────────────
    sections: Mapped[List["Section"]] = relationship(
        "Section",
        back_populates="book",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        return f"<Book id={self.id} title={self.title!r} status={self.ingestion_status}>"
