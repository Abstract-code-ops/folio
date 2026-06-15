"""Note session submission and note generation business logic.

Two flows:
  1. **Pasted notes** — creates a ``NoteSession`` record and enqueues
     a Dramatiq background job to run the similarity matching pass.
     Returns immediately with session + job IDs.
  2. **AI-generated notes** — streams note generation section-by-section
     via the LLM pipeline (not yet implemented — incoming in a later unit).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.note_session import NoteSession, NoteSessionStatus, NoteSource


# ── Pydantic response schemas ─────────────────────────────────


class NoteSessionResponse(BaseModel):
    """Returned after creating a new note session."""

    id: uuid.UUID
    book_id: uuid.UUID
    title: Optional[str] = None
    source: NoteSource
    status: NoteSessionStatus
    matched_section_count: Optional[int] = None
    job_id: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ── Service functions ──────────────────────────────────────────


async def create_note_session(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    book_id: uuid.UUID,
    raw_text: str,
    source: NoteSource,
    title: Optional[str] = None,
) -> NoteSessionResponse:
    """Create a note session and enqueue a background similarity job.

    Args:
        db: Async SQLAlchemy session.
        user_id: Authenticated user.
        book_id: Target book.
        raw_text: The pasted/typed note text.
        source: ``NoteSource.PASTED`` or ``NoteSource.AI_GENERATED``.
        title: Optional human-readable title.

    Returns:
        ``NoteSessionResponse`` with the session record and the
        Dramatiq job ID for status polling.
    """
    session = NoteSession(
        user_id=user_id,
        book_id=book_id,
        raw_text=raw_text,
        source=source,
        title=title,
        status=NoteSessionStatus.PENDING,
    )
    db.add(session)
    await db.flush()  # get the session.id

    # Enqueue background similarity job
    # Lazy import avoids pulling in Dramatiq broker at module load time.
    from app.workers.note_session import process_note_session  # noqa: C0301
    job = process_note_session.send(str(session.id))

    await db.commit()

    return NoteSessionResponse(
        id=session.id,
        book_id=session.book_id,
        title=session.title,
        source=session.source,
        status=session.status,
        matched_section_count=session.matched_section_count,
        job_id=job.message_id,
        created_at=session.created_at,
    )
