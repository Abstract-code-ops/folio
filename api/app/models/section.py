"""Section ORM model.

Each section represents a structural unit of a book — a chapter, a
subsection, or a connective passage. Sections form a hierarchy via
a self-referential parent_section_id and belong to exactly one book.

Section metadata (JSONB) is extracted once at ingestion time and
contains: learning_objectives, summary, concepts, definitions,
equations, examples, exercise_count. It is read at note generation
time but never updated after ingestion.

The pgvector embedding column stores a dense vector for coverage
similarity matching.
"""

import uuid
from typing import TYPE_CHECKING, Any, List, Optional

from sqlalchemy import Boolean, ForeignKey, Integer, SmallInteger, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, JSONB, TimestampMixin, Vector

if TYPE_CHECKING:
    from app.models.book import Book
    from app.models.chunk import Chunk


class Section(TimestampMixin, Base):
    __tablename__ = "section"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    book_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("book.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    parent_section_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("section.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # ── Hierarchy and ordering ────────────────────────────────
    chapter_index: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="0-based position of the chapter within the book",
    )
    section_index: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="0-based position of the section within its chapter; None for chapters",
    )
    level: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="0=chapter, 1=section, 2=subsection, etc.",
    )
    heading: Mapped[str] = mapped_column(
        String(512),
        nullable=False,
    )

    # ── Page range ────────────────────────────────────────────
    page_start: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    page_end: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    # ── Content and size ──────────────────────────────────────
    word_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    is_connective: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="True if word_count < 150 at parse time; rendered with reduced visual weight",
    )
    raw_text: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Full raw text of the section, used for Q&A retrieval and note generation",
    )

    # ── Metadata (extracted at ingestion, never updated) ──────
    section_metadata: Mapped[Optional[dict[str, Any]]] = mapped_column(
        "section_metadata",
        JSONB,
        nullable=True,
        comment=(
            "Structured metadata extracted at ingestion: "
            "{learning_objectives, summary, concepts, definitions, "
            "equations, examples, exercise_count}"
        ),
    )

    # ── Embedding (pgvector) ──────────────────────────────────
    embedding: Mapped[Optional[list[float]]] = mapped_column(
        Vector(768),
        nullable=True,
        comment="pgvector embedding for coverage similarity matching; dimension matches the configured embedding model",
    )

    # ── Embedding version ─────────────────────────────────────
    embed_version: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        default=1,
        server_default="1",
        comment="1 = embeddings built without task prefixes; 2 = nomic prefix inputs (U7)",
    )

    # ── Relationships ─────────────────────────────────────────
    book: Mapped["Book"] = relationship(
        "Book",
        back_populates="sections",
    )
    children: Mapped[List["Section"]] = relationship(
        "Section",
        back_populates="parent",
        cascade="all, delete-orphan",
    )
    parent: Mapped[Optional["Section"]] = relationship(
        "Section",
        back_populates="children",
        remote_side="Section.id",
    )
    chunks: Mapped[List["Chunk"]] = relationship(
        "Chunk",
        back_populates="section",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        return (
            f"<Section id={self.id} heading={self.heading!r} "
            f"level={self.level} pages={self.page_start}-{self.page_end}>"
        )
