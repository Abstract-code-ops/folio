"""Note session similarity pass background task definition.

Runs after a student submits a note session:
  1. Embed the pasted note text (sync LiteLLM call).
  2. Fetch all section embeddings for the session's book.
  3. Compute cosine similarity — find sections above threshold.
  4. Emit ``note_matched`` coverage events for each match.
  5. Update the session record with match count + status.
"""

from __future__ import annotations

import uuid

import dramatiq
from sqlalchemy import select

from app.core.db import SyncSessionLocal
from app.core.litellm import embed_text_sync
from app.models.coverage_event import CoverageEvent, EventType
from app.models.note_session import NoteSession, NoteSessionStatus
from app.models.section import Section
from app.pipeline.similarity import find_matching_sections


@dramatiq.actor(max_retries=3, min_backoff=10_000, max_backoff=60_000)
def process_note_session(session_id: str) -> None:
    """Process a note session: embed → match → emit events.

    Args:
        session_id: UUID string of the ``NoteSession`` to process.
    """
    parsed_id = uuid.UUID(session_id)

    with SyncSessionLocal() as db:
        try:
            # 1. Fetch the session
            session = db.get(NoteSession, parsed_id)
            if session is None:
                return   # nothing to process

            # Mark as processing
            session.status = NoteSessionStatus.PROCESSING
            db.flush()

            # 2. Embed the note text
            query_embedding = embed_text_sync(session.raw_text)

            # 3. Fetch section embeddings for the book
            section_rows = db.execute(
                select(Section.id, Section.embedding)
                .where(
                    Section.book_id == session.book_id,
                    Section.embedding.isnot(None),
                )
            ).all()

            section_embeddings: list[tuple[uuid.UUID, list[float]]] = [
                (row.id, row.embedding) for row in section_rows
                if row.embedding is not None and len(row.embedding) > 0
            ]

            # 4. Find matching sections
            matches = find_matching_sections(section_embeddings, query_embedding)

            # 5. Emit coverage events
            for section_id, score in matches:
                db.add(
                    CoverageEvent(
                        user_id=session.user_id,
                        book_id=session.book_id,
                        section_id=section_id,
                        event_type=EventType.NOTE_MATCHED,
                        event_metadata={
                            "note_session_id": str(session.id),
                            "similarity_score": round(score, 4),
                        },
                    )
                )

            # 6. Update session status
            session.matched_section_count = len(matches)
            session.status = NoteSessionStatus.COMPLETED
            db.commit()

        except Exception:
            session.status = NoteSessionStatus.FAILED
            db.commit()
            raise
