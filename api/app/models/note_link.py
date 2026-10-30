"""NoteLink ORM model.

A link points one block at a place in the book: a chunk, a section, a heading
path, a page range and a short excerpt.

**Why the citation is denormalised.** Re-ingestion deletes and recreates a
section's chunks (``workers/ingest.py``), so ``chunk_id`` is not a stable
identity. The heading path, page range and excerpt hash are stored alongside it
so a link survives that churn: ``chunk_id`` becomes NULL and the link can be
re-resolved from the anchor instead of silently disappearing.

Page numbers and excerpts are always produced by the server from the retrieved
chunk. A model never supplies either.
"""

from __future__ import annotations

import enum
import uuid
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.note_block import NoteBlock


class LinkStatus(str, enum.Enum):
    """Whether the student has seen and accepted this link."""

    SUGGESTED = "suggested"
    ACCEPTED = "accepted"
    DISMISSED = "dismissed"


class LinkOrigin(str, enum.Enum):
    """How the link was produced."""

    GENERATED = "generated"
    AUTO = "auto"
    MANUAL = "manual"


class NoteLink(TimestampMixin, Base):
    __tablename__ = "note_link"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    block_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("note_block.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    section_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("section.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # ── Denormalised anchor (survives re-ingestion) ───────────
    anchor_heading_path: Mapped[str] = mapped_column(
        String(512),
        nullable=False,
        comment="Ancestor headings joined with ' > ', e.g. 'Storage > B-trees'",
    )
    page_start: Mapped[int] = mapped_column(Integer, nullable=False)
    page_end: Mapped[int] = mapped_column(Integer, nullable=False)
    excerpt: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Built server-side from the chunk text, never by the model",
    )
    excerpt_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="sha256 of the normalised excerpt; the exact re-resolution key",
    )

    origin: Mapped[LinkOrigin] = mapped_column(
        SAEnum(
            LinkOrigin,
            name="note_link_origin",
            values_callable=lambda obj: [e.value for e in obj],
        ),
        nullable=False,
    )
    status: Mapped[LinkStatus] = mapped_column(
        SAEnum(
            LinkStatus,
            name="note_link_status",
            values_callable=lambda obj: [e.value for e in obj],
        ),
        default=LinkStatus.ACCEPTED,
        server_default=LinkStatus.ACCEPTED.value,
        nullable=False,
        index=True,
    )

    # ── Relationships ─────────────────────────────────────────
    block: Mapped["NoteBlock"] = relationship("NoteBlock", back_populates="links")

    def __repr__(self) -> str:
        return (
            f"<NoteLink id={self.id} block={self.block_id} "
            f"pages={self.page_start}-{self.page_end} status={self.status}>"
        )
