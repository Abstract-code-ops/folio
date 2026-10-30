"""Topic → note orchestration.

Retrieval, generation and validation in one pass, streamed as events so the
panel can show cards while the model is still writing. The business logic lives
here and the router just wraps the stream, which keeps the route handler thin.

Notes are local now: nothing is persisted here. The validated blocks are handed
back in the ``done`` event and the client stores them.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Any, AsyncGenerator, Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.chunk import Chunk
from app.models.note_block import BlockKind, BlockOrigin
from app.models.note_link import LinkOrigin
from app.pipeline.note_topic import (
    GeneratedTopicCard,
    GeneratedTopicNotes,
    TopicNotCovered,
    TopicNotesError,
    TopicNotesTruncated,
    TopicPassage,
    generate_topic_notes,
)
from app.services.notes import (
    NoteBlockDraft,
    NoteLinkDraft,
)
from app.services.retrieval import (
    Hit,
    breadcrumb,
    load_section_index,
    retrieve_top_chunks,
)

logger = logging.getLogger(__name__)

# Same budget as the chat citation chips, so an excerpt looks the same wherever
# it appears.
EXCERPT_CHARS = 240

NOT_COVERED_MESSAGE = (
    "This book doesn't cover that topic. Try a broader topic or a different book."
)


@dataclass(frozen=True)
class ResolvedPassage:
    """A retrieved chunk with everything a link and a prompt line need."""

    number: int
    chunk: Chunk
    heading_path: str
    page_start: int
    page_end: int

    def as_prompt_passage(self) -> TopicPassage:
        return TopicPassage(
            number=self.number,
            heading_path=self.heading_path,
            page_start=self.page_start,
            page_end=self.page_end,
            text=self.chunk.content or "",
        )


def _excerpt(text: str, limit: int = EXCERPT_CHARS) -> str:
    """A short quote from the chunk, cut on a word boundary.

    The server builds every excerpt: a model that supplied its own could quote
    something the book does not say.
    """
    collapsed = " ".join(text.split())
    if len(collapsed) <= limit:
        return collapsed
    cut = collapsed[:limit].rsplit(" ", 1)[0]
    return cut.rstrip(" ,.;:") + "..."


def _book_position(hit: Hit) -> tuple[int, int, int]:
    """Document order, so the notes follow the book rather than the ranking."""
    chunk = hit[0]
    section = chunk.section
    return (section.chapter_index, section.section_index or 0, chunk.chunk_index)


def _resolve_passages(
    hits: Sequence[Hit],
    index: dict[uuid.UUID, tuple[str, uuid.UUID | None]],
) -> list[ResolvedPassage]:
    """Order the hits by book position and number them within the word budget.

    Pure on purpose: the DB read happens once in the caller, so this is testable
    without a session.
    """
    resolved: list[ResolvedPassage] = []
    budget = settings.notes_topic_max_words

    for chunk, _distance in sorted(hits, key=_book_position):
        words = len((chunk.content or "").split())
        # Always keep the first passage, however long it is: a note needs at
        # least one source or there is nothing to write from.
        if resolved and words > budget:
            break
        budget -= words

        section = chunk.section
        resolved.append(
            ResolvedPassage(
                number=len(resolved) + 1,
                chunk=chunk,
                heading_path=breadcrumb(index, section.id),
                page_start=chunk.page_start or section.page_start,
                page_end=chunk.page_end or section.page_end,
            )
        )

    return resolved


def _card_text(card: GeneratedTopicCard) -> str:
    """Flatten a card into the block body a note stores.

    The block model has one text column, so the four fields become prose rather
    than a structured card. "Example:" is the only label kept, because it is the
    part a student scans for.
    """
    parts = [
        card.concept.strip(),
        card.definition.strip(),
        card.explanation.strip(),
    ]
    example = card.example.strip()
    if example:
        parts.append(f"Example: {example}")
    return "\n\n".join(part for part in parts if part)


def _blocks_from(
    notes: GeneratedTopicNotes,
    resolved: dict[int, ResolvedPassage],
) -> list[NoteBlockDraft]:
    """Turn validated cards into note blocks, one card per block."""
    blocks: list[NoteBlockDraft] = []

    for card in notes.cards:
        links: list[NoteLinkDraft] = []
        for number in card.sources:
            passage = resolved.get(number)
            # Already validated against the passage numbers, but a number that
            # cannot be resolved here must never become a link.
            if passage is None:
                continue
            links.append(
                NoteLinkDraft(
                    chunk_id=passage.chunk.id,
                    section_id=passage.chunk.section_id,
                    anchor_heading_path=passage.heading_path,
                    page_start=passage.page_start,
                    page_end=passage.page_end,
                    excerpt=_excerpt(passage.chunk.content or ""),
                    origin=LinkOrigin.GENERATED,
                )
            )

        if not links:
            continue

        blocks.append(
            NoteBlockDraft(
                kind=BlockKind.CARD,
                text=_card_text(card),
                origin=BlockOrigin.AI,
                links=links,
            )
        )

    gaps = [gap.strip() for gap in notes.gaps if gap.strip()]
    if gaps:
        blocks.append(
            NoteBlockDraft(
                kind=BlockKind.PARAGRAPH,
                # Each gap is its own sentence and already punctuated, so join
                # with a space rather than adding stray semicolons.
                text="Not covered by this book: " + " ".join(gaps),
                origin=BlockOrigin.AI,
            )
        )

    return blocks


def _card_event(index: int, card: GeneratedTopicCard) -> dict[str, Any]:
    return {
        "type": "card",
        "index": index,
        "concept": card.concept,
        "definition": card.definition,
        "explanation": card.explanation,
        "example": card.example,
        "sources": card.sources,
    }


async def stream_topic_note(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    book_id: uuid.UUID,
    topic: str,
) -> AsyncGenerator[dict[str, Any], None]:
    """Generate a note from a topic, yielding events as it goes.

    Events: ``card`` per validated card, ``gaps``, then either ``done`` with the
    note id or ``not_covered`` / ``error``. Nothing is persisted until every card
    has been validated, so a stream that dies mid-way leaves no half note.
    """
    hits = await retrieve_top_chunks(
        db, book_id, topic, k=settings.notes_topic_max_passages
    )
    if not hits:
        yield {"type": "not_covered", "message": NOT_COVERED_MESSAGE}
        return

    index, _rows = await load_section_index(db, book_id)
    passages = _resolve_passages(hits, index)

    try:
        notes = await generate_topic_notes(
            topic=topic,
            passages=[passage.as_prompt_passage() for passage in passages],
        )
    except TopicNotCovered as exc:
        logger.info("topic note declined for %r: %s", topic, exc)
        yield {"type": "not_covered", "message": NOT_COVERED_MESSAGE}
        return
    except TopicNotesTruncated as exc:
        logger.warning("topic note truncated for %r: %s", topic, exc)
        yield {
            "type": "error",
            "message": (
                "These notes were cut off before they finished. "
                "Try a narrower topic."
            ),
        }
        return
    except TopicNotesError as exc:
        logger.warning("topic note unusable for %r: %s", topic, exc)
        yield {
            "type": "error",
            "message": "The model's notes couldn't be used. Try again.",
        }
        return
    except Exception as exc:  # provider failure, timeout, unreadable response
        logger.warning("topic note generation failed for %r: %s", topic, exc)
        yield {"type": "error", "message": f"Couldn't generate notes: {exc}"}
        return

    for card_index, card in enumerate(notes.cards):
        yield _card_event(card_index, card)

    if notes.gaps:
        yield {"type": "gaps", "gaps": notes.gaps}

    blocks = _blocks_from(notes, {passage.number: passage for passage in passages})
    if not blocks:
        yield {"type": "not_covered", "message": NOT_COVERED_MESSAGE}
        return

    # Notes are local now: hand the validated blocks back for the client to
    # store, rather than persisting a row. `id` is excluded — the client
    # generates its own block ids (links attach to them).
    yield {
        "type": "done",
        "title": notes.title,
        "sections": len(
            {link.section_id for block in blocks for link in block.links}
        ),
        "blocks": [
            block.model_dump(mode="json", exclude={"id"}) for block in blocks
        ],
    }
