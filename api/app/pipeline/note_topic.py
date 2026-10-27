"""Topic note generation.

Takes numbered passages retrieved from one book and asks for structured study
notes that cite those passages by number.

The model never supplies a page, a quote or a heading path: the caller already
has them from retrieval, and the app attaches them. What this module does is
turn passages into a prompt and the reply into validated cards, dropping any
citation the passages cannot back.

A card carries concept, definition, explanation and example as text. The block
model stores one text column, so the caller assembles those four fields into the
block body -- no schema change, and the note view stays prose.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Sequence

from pydantic import BaseModel, ValidationError

from app.core.config import settings
from app.core.llm import NOTE_GEN_MODEL, void_acompletion
from app.pipeline.json_output import JsonOutputError, parse_json_object

logger = logging.getLogger(__name__)

# A topic that produces more than this is not narrower, just longer -- and a long
# reply is the one that gets cut off mid-JSON. The student can generate a second
# note for the rest.
MAX_CARDS = 6


class TopicNotesError(RuntimeError):
    """The reply could not be parsed, or nothing in it could be backed by a passage."""


class TopicNotCovered(TopicNotesError):
    """The passages do not support this topic.

    Separate from the parse failures above because it is not a fault: the caller
    says "not covered" to the student instead of reporting an error.
    """


class TopicNotesTruncated(TopicNotesError):
    """The reply hit the output limit and stopped mid-JSON.

    Distinct from a malformed reply because the advice differs: a garbled reply
    is worth retrying, a truncated one means the topic outstripped the budget.
    """


@dataclass(frozen=True)
class TopicPassage:
    """One retrieved passage, as the prompt numbers it."""

    number: int
    heading_path: str
    page_start: int
    page_end: int
    text: str


class GeneratedTopicCard(BaseModel):
    """One study-note card, with the passage numbers it rests on."""

    concept: str
    definition: str
    explanation: str
    example: str
    sources: list[int]


class GeneratedTopicNotes(BaseModel):
    """A whole topic note, before it becomes blocks."""

    title: str
    cards: list[GeneratedTopicCard]
    gaps: list[str] = []


SYSTEM_PROMPT = """You are a study-note generator for a single textbook. You will be given a topic and a numbered list of passages taken from that book.

Return one JSON object:

{
  "title": "a short title for the topic",
  "cards": [
    {
      "concept": "the concept's name",
      "definition": "one sentence defining it",
      "explanation": "a plain-language explanation, at most three sentences",
      "example": "one concrete example, drawn from the passages",
      "sources": [1, 4]
    }
  ],
  "gaps": ["what these passages do not explain"]
}

Rules:
- Use only the numbered passages. Never add outside knowledge.
- Every card lists the passage numbers it relies on in "sources", at least one.
- Never write citation markers such as [1] inside a text field; the app adds them.
- At most 6 cards. Prefer fewer, clearer cards over many thin ones.
- If the passages do not cover part of the topic, say so in "gaps" rather than filling it in.
- If nothing in the passages answers the topic, return an empty "cards" array and explain why in "gaps".
- Return only the JSON object, with no prose around it."""


def _pages(passage: TopicPassage) -> str:
    if passage.page_end == passage.page_start:
        return f"p. {passage.page_start}"
    return f"pp. {passage.page_start}-{passage.page_end}"


def build_user_prompt(topic: str, passages: Sequence[TopicPassage]) -> str:
    """Number every passage so the model can cite it by number."""
    lines = [f"# Topic\n{topic}\n", "# Passages\n"]
    for passage in passages:
        lines.append(
            f"[{passage.number}] ({passage.heading_path}, {_pages(passage)})\n"
            f"{passage.text}\n"
        )
    lines.append("Return the JSON object described in the instructions.")
    return "\n".join(lines)


def _keep_backed_cards(
    cards: Sequence[GeneratedTopicCard],
    passage_numbers: set[int],
) -> tuple[list[GeneratedTopicCard], int]:
    """Drop citation numbers the passages cannot back, then cards left uncited.

    Returns the kept cards and how many were dropped, so the caller can log it --
    a silent drop would look like the model simply wrote less.
    """
    kept: list[GeneratedTopicCard] = []
    dropped = 0

    for card in cards:
        if not card.concept.strip() or not card.definition.strip():
            dropped += 1
            continue

        sources = sorted(
            {number for number in card.sources if number in passage_numbers}
        )
        if not sources:
            dropped += 1
            continue

        kept.append(card.model_copy(update={"sources": sources}))

    return kept, dropped


async def generate_topic_notes(
    *,
    topic: str,
    passages: Sequence[TopicPassage],
    model: str | None = None,
) -> GeneratedTopicNotes:
    """Generate a topic note from already-retrieved passages.

    Raises ``TopicNotCovered`` when the passages cannot support the topic and
    ``TopicNotesTruncated`` when the reply ran out of output budget: both are
    decisions for the caller, not faults.
    """
    if not passages:
        raise TopicNotesError("no passages to generate from")

    response = await void_acompletion(
        model=model or NOTE_GEN_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_user_prompt(topic, passages)},
        ],
        response_format={"type": "json_object"},
        temperature=0.3,
        # Explicit budget: the provider's default cuts a full set of cards off
        # mid-JSON, which surfaces as a parse failure rather than a short answer.
        max_tokens=settings.notes_topic_max_tokens,
    )

    choice = response.choices[0]
    content = choice.message.content
    try:
        payload = parse_json_object(content, context=f"topic notes for {topic!r}")
    except JsonOutputError as exc:
        if getattr(choice, "finish_reason", None) == "length":
            raise TopicNotesTruncated(
                f"topic notes for {topic!r} were cut off at the token limit"
            ) from exc
        raise TopicNotesError(str(exc)) from exc

    try:
        parsed = GeneratedTopicNotes.model_validate(payload)
    except ValidationError as exc:
        raise TopicNotesError(
            f"topic notes for {topic!r} did not return the expected shape: "
            f"{exc.error_count()} validation error(s)"
        ) from exc

    passage_numbers = {passage.number for passage in passages}
    cards, dropped = _keep_backed_cards(parsed.cards[:MAX_CARDS], passage_numbers)
    if dropped:
        logger.warning(
            "dropped %d card(s) with no backing passage for topic %r",
            dropped,
            topic,
        )

    if not cards:
        # The passages did not support the topic: a "not covered", not a crash.
        raise TopicNotCovered(
            f"topic notes for {topic!r} produced no card backed by a passage"
        )

    return GeneratedTopicNotes(title=parsed.title, cards=cards, gaps=parsed.gaps)
