"""Tests for the topic-note service helpers.

Deliberately narrow: retrieval and streaming need a database and a model, which
is what the live check covers. These pin the parts that decide what the note
contains -- document order, the word budget, the excerpt, the block body, and
which citations survive into links.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from app.core.config import settings
from app.pipeline.note_topic import GeneratedTopicCard, GeneratedTopicNotes
from app.services import note_topic as service
from app.services.note_topic import (
    EXCERPT_CHARS,
    ResolvedPassage,
    _blocks_from,
    _card_text,
    _excerpt,
    _resolve_passages,
)


def _section(*, chapter: int, index: int | None, pages: tuple[int, int]):
    return SimpleNamespace(
        id=uuid.uuid4(),
        chapter_index=chapter,
        section_index=index,
        page_start=pages[0],
        page_end=pages[1],
    )


def _chunk(
    *,
    section,
    content: str,
    pages: tuple[int, int] | None = None,
    chunk_index: int = 0,
):
    return SimpleNamespace(
        id=uuid.uuid4(),
        section_id=section.id,
        section=section,
        content=content,
        chunk_index=chunk_index,
        page_start=pages[0] if pages else None,
        page_end=pages[1] if pages else None,
    )


def _hit(chunk, distance: float = 0.2):
    return (chunk, distance)


# ── Document order and the word budget ────────────────────────


def test_passages_are_numbered_in_book_order_not_rank_order():
    """Notes should read like the book, so position wins over distance."""
    first = _section(chapter=1, index=0, pages=(10, 20))
    second = _section(chapter=2, index=0, pages=(30, 40))
    later = _chunk(section=second, content="second chapter text")
    earlier = _chunk(section=first, content="first chapter text")

    # Retrieval order (best distance first) is deliberately the wrong order.
    resolved = _resolve_passages([_hit(later, 0.1), _hit(earlier, 0.3)], {})

    assert [passage.chunk.content for passage in resolved] == [
        "first chapter text",
        "second chapter text",
    ]
    assert [passage.number for passage in resolved] == [1, 2]


def test_the_word_budget_stops_adding_passages(monkeypatch: pytest.MonkeyPatch):
    # 10 words of budget: the first chunk takes 3, leaving 7, so a 20-word
    # chunk cannot join it.
    monkeypatch.setattr(settings, "notes_topic_max_words", 10)
    section = _section(chapter=1, index=0, pages=(1, 9))
    small = _chunk(section=section, content="one two three", chunk_index=0)
    too_big = _chunk(
        section=section, content=" ".join(["word"] * 20), chunk_index=1
    )

    resolved = _resolve_passages([_hit(small), _hit(too_big)], {})

    assert len(resolved) == 1
    assert resolved[0].chunk.content == "one two three"


def test_the_first_passage_is_kept_even_over_budget(monkeypatch: pytest.MonkeyPatch):
    """A note with no source would have nothing to say."""
    monkeypatch.setattr(settings, "notes_topic_max_words", 1)
    section = _section(chapter=1, index=0, pages=(1, 9))
    long_chunk = _chunk(section=section, content=" ".join(["word"] * 50))

    resolved = _resolve_passages([_hit(long_chunk)], {})

    assert len(resolved) == 1


def test_chunk_pages_win_over_section_pages():
    section = _section(chapter=1, index=0, pages=(1, 99))
    chunk = _chunk(section=section, content="x", pages=(40, 42))

    resolved = _resolve_passages([_hit(chunk)], {})

    assert (resolved[0].page_start, resolved[0].page_end) == (40, 42)


def test_section_pages_are_the_fallback_when_a_chunk_has_none():
    section = _section(chapter=1, index=0, pages=(1, 99))
    chunk = _chunk(section=section, content="x")

    resolved = _resolve_passages([_hit(chunk)], {})

    assert (resolved[0].page_start, resolved[0].page_end) == (1, 99)


def test_the_heading_path_comes_from_the_section_index():
    parent = uuid.uuid4()
    section = _section(chapter=1, index=0, pages=(1, 9))
    index = {
        section.id: ("B-trees", parent),
        parent: ("Storage engines", None),
    }

    resolved = _resolve_passages(
        [_hit(_chunk(section=section, content="x"))], index
    )

    assert resolved[0].heading_path == "Storage engines > B-trees"


# ── Excerpts ──────────────────────────────────────────────────


def test_a_short_chunk_is_quoted_whole():
    assert _excerpt("B-trees keep keys sorted.") == "B-trees keep keys sorted."


def test_a_long_chunk_is_cut_on_a_word_boundary():
    text = " ".join(["word"] * 200)

    excerpt = _excerpt(text)

    assert len(excerpt) <= EXCERPT_CHARS + 3
    assert excerpt.endswith("...")
    assert "  " not in excerpt


def test_whitespace_in_a_chunk_is_collapsed():
    assert _excerpt("line one\n\n  line two") == "line one line two"


# ── The block body ────────────────────────────────────────────


def _card(**overrides) -> GeneratedTopicCard:
    fields = {
        "concept": "B-tree",
        "definition": "A self-balancing search tree.",
        "explanation": "It keeps keys ordered so a lookup reads few pages.",
        "example": "A page of sorted keys.",
        "sources": [1],
    }
    fields.update(overrides)
    return GeneratedTopicCard(**fields)


def test_the_block_body_is_the_four_fields_as_prose():
    text = _card_text(_card())

    assert text.startswith("B-tree\n\nA self-balancing search tree.")
    assert "Example: A page of sorted keys." in text


def test_an_empty_example_adds_no_label():
    text = _card_text(_card(example=""))

    assert "Example:" not in text


# ── Blocks and links ──────────────────────────────────────────


def _resolved(number: int, *, section, pages=(10, 12)) -> ResolvedPassage:
    return ResolvedPassage(
        number=number,
        chunk=_chunk(section=section, content="B-trees keep keys sorted.", pages=pages),
        heading_path="Storage engines > B-trees",
        page_start=pages[0],
        page_end=pages[1],
    )


def test_each_card_becomes_a_block_with_one_link_per_source():
    section = _section(chapter=1, index=0, pages=(10, 12))
    resolved = {1: _resolved(1, section=section), 2: _resolved(2, section=section)}
    notes = GeneratedTopicNotes(title="B-trees", cards=[_card(sources=[1, 2])], gaps=[])

    blocks = _blocks_from(notes, resolved)

    assert len(blocks) == 1
    assert blocks[0].kind.value == "card"
    assert len(blocks[0].links) == 2
    assert blocks[0].links[0].page_start == 10
    assert blocks[0].links[0].excerpt.startswith("B-trees keep keys sorted.")


def test_a_card_whose_sources_cannot_be_resolved_is_dropped():
    section = _section(chapter=1, index=0, pages=(10, 12))
    notes = GeneratedTopicNotes(title="x", cards=[_card(sources=[7])], gaps=[])

    blocks = _blocks_from(notes, {1: _resolved(1, section=section)})

    assert blocks == []


def test_gaps_become_a_closing_paragraph():
    section = _section(chapter=1, index=0, pages=(10, 12))
    notes = GeneratedTopicNotes(
        title="B-trees",
        cards=[_card()],
        gaps=["The cost of updates.", "Write amplification."],
    )

    blocks = _blocks_from(notes, {1: _resolved(1, section=section)})

    assert blocks[-1].kind.value == "paragraph"
    assert "Not covered by this book:" in blocks[-1].text
    assert "Write amplification." in blocks[-1].text


def test_no_gaps_means_no_closing_paragraph():
    section = _section(chapter=1, index=0, pages=(10, 12))
    notes = GeneratedTopicNotes(title="B-trees", cards=[_card()], gaps=[])

    blocks = _blocks_from(notes, {1: _resolved(1, section=section)})

    assert len(blocks) == 1
