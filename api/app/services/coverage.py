"""Coverage map retrieval and event emission business logic.

Coverage scores are derived entirely from accumulated events — no LLM
is involved. Every user interaction that touches a section emits an
event row, and the score for a section is the sum of point values
across all events for that (user_id, section_id) pair, capped at 15.

Visual states (defined in docs/ui-context.md):
  0     → uncovered
  1–4   → mentioned
  5–9   → partial
  10–15 → well_covered
"""

from __future__ import annotations

import uuid
from typing import Optional

from pydantic import BaseModel, ConfigDict
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.coverage_event import CoverageEvent, EventType
from app.models.section import Section


# ── Coverage state derivation ─────────────────────────────────


COVERAGE_CAP = settings.coverage_score_cap  # 15

# Map event types to their point values from config
EVENT_POINT_MAP: dict[EventType, int] = {
    EventType.PAGE_VIEWED: settings.coverage_points_page_viewed,
    EventType.NOTE_MATCHED: settings.coverage_points_note_matched,
    EventType.NOTES_GENERATED: settings.coverage_points_notes_generated,
    EventType.QA_ASKED: settings.coverage_points_qa_asked,
    EventType.QUIZ_ANSWERED: settings.coverage_points_quiz_answered,
}


def coverage_state_from_score(score: int) -> str:
    """Map a numeric score to its named visual state.

    See docs/ui-context.md for the canonical state-to-visual mapping.
    """
    if score <= 0:
        return "uncovered"
    if score <= 4:
        return "mentioned"
    if score <= 9:
        return "partial"
    return "well_covered"


# ── Pydantic response schemas ─────────────────────────────────


class SectionCoverage(BaseModel):
    """Coverage state for a single section in the coverage map."""

    id: uuid.UUID
    book_id: uuid.UUID
    parent_section_id: Optional[uuid.UUID] = None
    chapter_index: int
    section_index: Optional[int] = None
    level: int
    heading: str
    page_start: int
    page_end: int
    word_count: int
    is_connective: bool
    coverage_score: int
    coverage_state: str
    key_terms: list[str] = []

    model_config = ConfigDict(from_attributes=True)


class CoverageMapResponse(BaseModel):
    """Full coverage map for one book — section tree + per-section scores."""

    book_id: uuid.UUID
    sections: list[SectionCoverage]


# ── Service functions ──────────────────────────────────────────


async def get_coverage_map(
    db: AsyncSession,
    user_id: uuid.UUID,
    book_id: uuid.UUID,
) -> CoverageMapResponse:
    """Build the full coverage map for *book_id* scoped to *user_id*.

    Returns every section of the book (ordered by chapter then section
    position) with its aggregated coverage score and derived visual state.
    """
    # Single query: sections LEFT JOIN their coverage events (filtered to this
    # user + book in the ON clause). One round trip instead of two; rows for a
    # section are contiguous thanks to the ORDER BY, so we fold them in Python
    # (point values stay env-configurable via settings).
    query = (
        select(Section, CoverageEvent.event_type)
        .outerjoin(
            CoverageEvent,
            (CoverageEvent.section_id == Section.id)
            & (CoverageEvent.user_id == user_id)
            & (CoverageEvent.book_id == book_id),
        )
        .where(Section.book_id == book_id)
        .order_by(Section.chapter_index, Section.section_index, Section.id)
    )
    rows = (await db.execute(query)).all()

    def build(section: Section, value: int) -> SectionCoverage:
        key_terms: list[str] = []
        if section.section_metadata and "concepts" in section.section_metadata:
            key_terms = section.section_metadata["concepts"]
        return SectionCoverage(
            id=section.id,
            book_id=section.book_id,
            parent_section_id=section.parent_section_id,
            chapter_index=section.chapter_index,
            section_index=section.section_index,
            level=section.level,
            heading=section.heading,
            page_start=section.page_start,
            page_end=section.page_end,
            word_count=section.word_count,
            is_connective=section.is_connective,
            coverage_score=value,
            coverage_state=coverage_state_from_score(value),
            key_terms=key_terms,
        )

    section_coverages: list[SectionCoverage] = []
    current: Optional[Section] = None
    score = 0
    for section, event_type in rows:
        if current is None or section.id != current.id:
            if current is not None:
                section_coverages.append(build(current, score))
            current = section
            score = 0
        if event_type is not None:
            score = min(score + EVENT_POINT_MAP.get(event_type, 0), COVERAGE_CAP)

    if current is not None:
        section_coverages.append(build(current, score))

    return CoverageMapResponse(
        book_id=book_id,
        sections=section_coverages,
    )
