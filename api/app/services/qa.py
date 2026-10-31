"""Grounded Q&A business logic.

Retrieval is pgvector cosine distance over a book's chunks, with the query
embedded through Ollama's nomic-embed-text. Retrieval v2 (plan unit U8) adds:

- the nomic ``search_query:`` prefix behind ``embed_prefixes_enabled``, together
  with an ``embed_version`` restriction so documents and queries are never in
  different embedding spaces;
- the real cosine distance returned with every hit, instead of a placeholder;
- an optional ``retrieval_max_distance`` cut-off, disabled by default;
- optional dedup by section, and optional exclusion of connective stubs;
- optional context expansion: neighbouring chunks and the parent section's
  summary, each marked with its role.

Plan unit U9 needs each passage to carry its heading path and the headings
around it; plan unit U10 needs the page range of the chunk itself, so a citation
can point at the passage rather than at the whole section.

Every toggle defaults to the behaviour that was measured on the eval.
"""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass, replace
from typing import Any, Optional, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.config import settings
from app.models.book import Book
from app.models.chunk import Chunk
from app.models.qa_message import QAMessage
from app.models.section import Section

# Retrieval lives in its own module so notes can share it without a service
# importing a service. Re-exported here because the router, the eval runner and
# the retrieval tests import these names from this module.
from app.services.retrieval import (
    Hit,
    breadcrumb as _breadcrumb,
    load_section_index as _section_index,
    retrieve_top_chunks,
)

logger = logging.getLogger(__name__)

TOP_K_CHUNKS = 5
EXCERPT_CHARS = 240

ROLE_MATCH = "match"
ROLE_CONTEXT = "context"

# A passage reference the answer wrote, e.g. "[1]" or "[12]".
CITATION_TAG_RE = re.compile(r"\[(\d{1,3})\]")


@dataclass(frozen=True)
class ContextPassage:
    """One passage handed to the context builder.

    Shaped like a ``Chunk`` for the two attributes ``build_context`` reads --
    ``section`` and ``content`` -- so context expansion does not force a rewrite
    of the prompt builder. ``breadcrumb``, ``siblings`` and ``note`` are what
    U9's format needs; ``page_start``/``page_end`` are the chunk's own pages,
    which U10 prefers over the section's wider range.
    """

    section: Section
    content: str
    role: str = ROLE_CONTEXT
    distance: Optional[float] = None
    chunk_index: Optional[int] = None
    breadcrumb: str = ""
    siblings: tuple[tuple[str, bool], ...] = ()
    note: str = ""
    page_start: Optional[int] = None
    page_end: Optional[int] = None


def _siblings(
    rows: list,
    index: dict[uuid.UUID, tuple[str, Optional[uuid.UUID]]],
    section_id: uuid.UUID,
    matched: set[uuid.UUID],
) -> tuple[tuple[str, bool], ...]:
    """Headings sharing this section's parent, in document order."""
    entry = index.get(section_id)
    if entry is None:
        return ()
    parent = entry[1]
    return tuple(
        (heading, sibling_id in matched)
        for sibling_id, heading, sibling_parent in rows
        if sibling_parent == parent
    )


async def expand_context(
    db: AsyncSession,
    hits: list[Hit],
    *,
    include_neighbours: bool | None = None,
    include_parent_summary: bool | None = None,
) -> list[ContextPassage]:
    """Turn matches into the passage list handed to the context builder.

    Matches come first, in distance order, then any expansion marked as
    context. Every passage carries its heading path, the headings around it, and
    its own page range when it has one, so neither the prompt builder nor the
    citation builder has to query again.
    """
    if include_neighbours is None:
        include_neighbours = settings.retrieval_expand_neighbours
    if include_parent_summary is None:
        include_parent_summary = settings.retrieval_parent_context

    if not hits:
        return []

    index, rows = await _section_index(db, hits[0][0].section.book_id)
    matched = {chunk.section_id for chunk, _distance in hits}

    def passage(
        section: Section,
        content: str,
        *,
        role: str,
        distance: Optional[float] = None,
        chunk_index: Optional[int] = None,
        note: str = "",
        page_start: Optional[int] = None,
        page_end: Optional[int] = None,
    ) -> ContextPassage:
        return ContextPassage(
            section=section,
            content=content,
            role=role,
            distance=distance,
            chunk_index=chunk_index,
            breadcrumb=_breadcrumb(index, section.id),
            siblings=_siblings(rows, index, section.id, matched),
            note=note,
            page_start=page_start,
            page_end=page_end,
        )

    passages: list[ContextPassage] = [
        passage(
            chunk.section,
            chunk.content,
            role=ROLE_MATCH,
            distance=distance,
            chunk_index=chunk.chunk_index,
            page_start=chunk.page_start,
            page_end=chunk.page_end,
        )
        for chunk, distance in hits
    ]

    if not (include_neighbours or include_parent_summary):
        return passages

    section_ids = {chunk.section_id for chunk, _distance in hits}

    if include_neighbours:
        siblings = (
            (
                await db.execute(
                    select(Chunk)
                    .where(Chunk.section_id.in_(section_ids))
                    .options(joinedload(Chunk.section))
                )
            )
            .unique()
            .scalars()
            .all()
        )
        by_position = {
            (chunk.section_id, chunk.chunk_index): chunk for chunk in siblings
        }
        already = {chunk.id for chunk, _distance in hits}
        for chunk, _distance in hits:
            for offset in (-1, 1):
                neighbour = by_position.get(
                    (chunk.section_id, chunk.chunk_index + offset)
                )
                if neighbour is None or neighbour.id in already:
                    continue
                already.add(neighbour.id)
                passages.append(
                    passage(
                        neighbour.section,
                        neighbour.content,
                        role=ROLE_CONTEXT,
                        chunk_index=neighbour.chunk_index,
                        note="neighbouring passage",
                        page_start=neighbour.page_start,
                        page_end=neighbour.page_end,
                    )
                )

    if include_parent_summary:
        parent_ids = {
            chunk.section.parent_section_id
            for chunk, _distance in hits
            if chunk.section.parent_section_id is not None
        }
        if parent_ids:
            parents = (
                (await db.execute(select(Section).where(Section.id.in_(parent_ids))))
                .scalars()
                .all()
            )
            for parent in parents:
                summary = (parent.section_metadata or {}).get("summary")
                if not summary:
                    continue
                passages.append(
                    passage(
                        parent,
                        summary.strip(),
                        role=ROLE_CONTEXT,
                        note="opening of parent section",
                    )
                )

    return passages


# ── Citation and turn history (U10, eval page) ────────────────


def build_turn_diagnostics(
    *,
    mode: str,
    queries: Sequence[str],
    passages: Sequence[ContextPassage],
    citation_count: int,
    answer_chars: int,
    error: Optional[str],
    reasoning: str = "",
    ttft_ms: Optional[int] = None,
    total_ms: Optional[int] = None,
) -> dict[str, Any]:
    """Record what happened during a turn, for the eval page.

    Everything here is measured after the fact: no extra model call, no extra
    query. ``retrieved`` keeps the distance so a bad answer can be told apart
    from a good answer that retrieval never supported.
    """
    if mode == "agent":
        action = "searched_book" if queries else "answered_without_retrieval"
    else:
        action = "retrieved"

    return {
        "mode": mode,
        "action": action,
        "queries": list(queries),
        "retrieved": [
            {
                "role": passage.role,
                "heading": passage.section.heading,
                "breadcrumb": passage.breadcrumb,
                "page_start": (
                    passage.page_start
                    if passage.page_start is not None
                    else passage.section.page_start
                ),
                "page_end": (
                    passage.page_end
                    if passage.page_end is not None
                    else passage.section.page_end
                ),
                "chunk_index": passage.chunk_index,
                "distance": passage.distance,
            }
            for passage in passages
        ],
        "citations": citation_count,
        "answer_chars": answer_chars,
        "reasoning": reasoning,
        "ttft_ms": ttft_ms,
        "total_ms": total_ms,
        "error": error,
    }


async def list_recent_turns(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    book_id: Optional[uuid.UUID] = None,
    limit: int = 50,
) -> list[tuple[QAMessage, Optional[str]]]:
    """Recent Q&A turns with their book title, newest first."""
    stmt = (
        select(QAMessage, Book.title)
        .outerjoin(Book, Book.id == QAMessage.book_id)
        .where(QAMessage.user_id == user_id)
        .order_by(QAMessage.created_at.desc())
        .limit(max(1, min(limit, 200)))
    )
    if book_id is not None:
        stmt = stmt.where(QAMessage.book_id == book_id)
    return [(row[0], row[1]) for row in (await db.execute(stmt)).all()]


def _citation_event(number: int, passage: ContextPassage) -> dict[str, Any]:
    """Build one citation event from a passage.

    Uses the chunk's own page range when it has one, falling back to the
    section's range for books ingested before chunks carried pages.
    """
    section = passage.section
    page_start = passage.page_start if passage.page_start is not None else section.page_start
    page_end = passage.page_end if passage.page_end is not None else section.page_end

    excerpt = passage.content.strip()
    if len(excerpt) > EXCERPT_CHARS:
        excerpt = excerpt[:EXCERPT_CHARS].rstrip() + "..."

    return {
        "type": "citation",
        "passage": number,
        "chunk_index": passage.chunk_index,
        "section_heading": section.heading,
        "page_start": page_start,
        "page_end": page_end,
        "excerpt": excerpt,
    }


def build_used_citations(
    answer: str,
    passages: Sequence[ContextPassage],
) -> list[dict[str, Any]]:
    """Citations for the passages the answer actually cited.

    Passages are numbered as the prompt numbers them -- 1-based over the whole
    passage list -- so a cited number indexes straight in. Only match passages
    can be cited: a context passage is not a source, and a model that cites one
    is ignored rather than given a citation.

    If the answer cites nothing usable, fall back to the top-ranked match and
    log it, so a citation-less answer still surfaces its best source.
    """
    match_by_number = {
        index + 1: passage
        for index, passage in enumerate(passages)
        if passage.role == ROLE_MATCH
    }

    cited: list[int] = []
    seen: set[int] = set()
    for raw in CITATION_TAG_RE.findall(answer or ""):
        number = int(raw)
        if number in seen or number not in match_by_number:
            continue
        seen.add(number)
        cited.append(number)

    if not cited:
        if not match_by_number:
            return []
        fallback = min(match_by_number)
        logger.warning(
            "Answer cited no usable passage number; falling back to the "
            "top-ranked match [%d] (%s)",
            fallback,
            match_by_number[fallback].section.heading,
        )
        cited = [fallback]

    return [_citation_event(number, match_by_number[number]) for number in cited]
