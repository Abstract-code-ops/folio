"""NoteBlock ORM model.

A note is an ordered list of blocks. A link always attaches to a block, never
to a character offset, so editing earlier text cannot drag a citation onto the
wrong sentence.

The kinds are deliberately flat: heading, paragraph, bullet, card. Infinite
nesting is the one feature every block editor offers and book notes never need
-- a flat list keeps ordering, linking and autosave simple.
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
    from app.models.note_link import NoteLink
    from app.models.note_session import NoteSession


class BlockKind(str, enum.Enum):
    """What the block renders as."""

    HEADING = "heading"
    PARAGRAPH = "paragraph"
    BULLET = "bullet"
    CARD = "card"


class BlockOrigin(str, enum.Enum):
    """Where the text came from.

    The linking step is input-agnostic and ignores this; it exists so scanned
    paper notes need no redesign later.
    """

    TYPED = "typed"
    AI = "ai"
    OCR = "ocr"


class NoteBlock(TimestampMixin, Base):
    __tablename__ = "note_block"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    note_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("note_session.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    position: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="0-based position of this block within its note",
    )
    kind: Mapped[BlockKind] = mapped_column(
        SAEnum(
            BlockKind,
            name="note_block_kind",
            values_callable=lambda obj: [e.value for e in obj],
        ),
        nullable=False,
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        comment="sha256 of the normalised text; autosave skips unchanged blocks",
    )
    origin: Mapped[BlockOrigin] = mapped_column(
        SAEnum(
            BlockOrigin,
            name="note_block_origin",
            values_callable=lambda obj: [e.value for e in obj],
        ),
        default=BlockOrigin.TYPED,
        server_default=BlockOrigin.TYPED.value,
        nullable=False,
    )

    # ── Relationships ─────────────────────────────────────────
    note: Mapped["NoteSession"] = relationship(
        "NoteSession",
        back_populates="blocks",
    )
    links: Mapped[list["NoteLink"]] = relationship(
        "NoteLink",
        back_populates="block",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        return (
            f"<NoteBlock id={self.id} note={self.note_id} "
            f"pos={self.position} kind={self.kind}>"
        )
