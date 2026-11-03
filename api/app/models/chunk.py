"""Chunk ORM model.

Chunks are hierarchy-aware text fragments of a section, created at
ingestion time. They never cross section boundaries. Each chunk
carries its own pgvector embedding for Q&A retrieval — the Q&A
pipeline retrieves top-k chunks from the currently open section to
ground its answers.
"""

import uuid
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import ForeignKey, Integer, SmallInteger, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, JSONB, TimestampMixin, Vector

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
        Vector(768),
        nullable=True,
        comment="pgvector embedding for Q&A retrieval; dimension matches configured embedding model",
    )

    # ── Page range ────────────────────────────────────────────
    page_start: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="First page covered by the chunk; NULL for rows ingested before parser v2",
    )
    page_end: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Last page covered by the chunk; NULL for rows ingested before parser v2",
    )

    # ── Embedding version ─────────────────────────────────────
    embed_version: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        default=1,
        server_default="1",
        comment="1 = embeddings built without task prefixes; 2 = nomic prefix inputs (U7)",
    )

    # ── Chunk type ────────────────────────────────────────────
    kind: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="text",
        server_default="'text'",
        comment="'text' | 'table' | 'figure'; a table chunk is Markdown and is embedded/rendered as structured data",
    )

    # Figure region (kind='figure' only): {x0,y0,x1,y1} in page points. The
    # caption lives in ``content``; no image is stored.
    bbox: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=True,
        comment="Figure region {x0,y0,x1,y1} in PDF points; kind='figure' only",
    )

    # ── Relationships ─────────────────────────────────────────
    section: Mapped["Section"] = relationship(
        "Section",
        back_populates="chunks",
    )

    def __repr__(self) -> str:
        return f"<Chunk id={self.id} section={self.section_id} index={self.chunk_index}>"
