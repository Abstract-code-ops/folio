"""Chunk ORM model.

Chunks are hierarchy-aware text fragments of a section, created at
ingestion time. They never cross section boundaries. Each chunk
carries its own pgvector embedding for Q&A retrieval — the Q&A
pipeline retrieves top-k chunks from the currently open section to
ground its answers.
"""

import uuid
from typing import TYPE_CHECKING, Optional

from sqlalchemy import ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, TimestampMixin, Vector

if TYPE_CHECKING:
    from app.models.section import Section


class Chunk(TimestampMixin, Base):
    __tablename__ = "chunk"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    section_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("section.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chunk_index: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="0-based position of this chunk within its section",
    )
    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Chunk text content, never crosses a section boundary",
    )
    embedding: Mapped[Optional[list[float]]] = mapped_column(
        Vector(1536),
        nullable=True,
        comment="pgvector embedding for Q&A retrieval; dimension matches configured embedding model",
    )

    # ── Relationships ─────────────────────────────────────────
    section: Mapped["Section"] = relationship(
        "Section",
        back_populates="chunks",
    )

    def __repr__(self) -> str:
        return f"<Chunk id={self.id} section={self.section_id} index={self.chunk_index}>"
