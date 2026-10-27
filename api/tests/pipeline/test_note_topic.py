"""Tests for topic note generation.

The model is stubbed: these pin what happens to a reply, not whether the model
is any good. The contract is that no citation survives unless a retrieved passage
backs it, and that a reply with nothing usable surfaces as ``TopicNotCovered``
rather than as a card with an invented source.
"""

from __future__ import annotations

import pytest

from app.core.config import settings
from app.pipeline import note_topic
from app.pipeline.note_topic import (
    MAX_CARDS,
    TopicNotCovered,
    TopicNotesError,
    TopicNotesTruncated,
    TopicPassage,
    build_user_prompt,
    generate_topic_notes,
)


class _Message:
    def __init__(self, content: str) -> None:
        self.content = content


class _Choice:
    def __init__(self, content: str, finish_reason: str) -> None:
        self.message = _Message(content)
        self.finish_reason = finish_reason


class _Response:
    def __init__(self, content: str, finish_reason: str) -> None:
        self.choices = [_Choice(content, finish_reason)]


def _stub_reply(
    monkeypatch: pytest.MonkeyPatch,
    content: str,
    finish_reason: str = "stop",
) -> None:
    async def fake(**kwargs):
        return _Response(content, finish_reason)

    monkeypatch.setattr(note_topic, "void_acompletion", fake)


def _passages() -> list[TopicPassage]:
    return [
        TopicPassage(
            number=1,
            heading_path="Storage engines > B-trees",
            page_start=99,
            page_end=103,
            text="B-trees keep keys sorted inside fixed-size pages.",
        ),
        TopicPassage(
            number=2,
            heading_path="Storage engines > LSM-trees",
            page_start=104,
            page_end=108,
            text="LSM-trees append to a log and merge in the background.",
        ),
    ]


def _card(
    *,
    concept: str = "B-tree",
    sources: str = "[1]",
    definition: str = "A balanced search tree.",
) -> str:
    return (
        "{"
        f'"concept": "{concept}", '
        f'"definition": "{definition}", '
        '"explanation": "It keeps keys ordered so a lookup reads a few pages.", '
        '"example": "A page holding sorted keys.", '
        f'"sources": {sources}'
        "}"
    )


def _payload(cards: str, gaps: str = '["The cost of updates."]') -> str:
    return (
        '{"title": "B-trees and LSM-trees", '
        f'"cards": [{cards}], "gaps": {gaps}}}'
    )


async def test_cards_keep_their_sources(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_reply(monkeypatch, _payload(_card(sources="[1, 2]")))

    notes = await generate_topic_notes(topic="B-trees", passages=_passages())

    assert notes.title == "B-trees and LSM-trees"
    assert len(notes.cards) == 1
    assert notes.cards[0].sources == [1, 2]
    assert notes.gaps == ["The cost of updates."]


async def test_sources_outside_the_passages_are_dropped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A citation the book cannot back must not survive, even if the card does."""
    _stub_reply(monkeypatch, _payload(_card(sources="[1, 9]")))

    notes = await generate_topic_notes(topic="B-trees", passages=_passages())

    assert notes.cards[0].sources == [1]


async def test_duplicate_sources_collapse(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_reply(monkeypatch, _payload(_card(sources="[2, 2, 1]")))

    notes = await generate_topic_notes(topic="B-trees", passages=_passages())

    assert notes.cards[0].sources == [1, 2]


async def test_a_card_with_no_backed_source_is_dropped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cards = ", ".join([_card(sources="[9]"), _card(concept="LSM-tree", sources="[2]")])
    _stub_reply(monkeypatch, _payload(cards))

    notes = await generate_topic_notes(topic="Trees", passages=_passages())

    assert [card.concept for card in notes.cards] == ["LSM-tree"]


async def test_a_card_without_a_concept_is_dropped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cards = ", ".join([_card(concept=" ", sources="[1]"), _card(sources="[1]")])
    _stub_reply(monkeypatch, _payload(cards))

    notes = await generate_topic_notes(topic="Trees", passages=_passages())

    assert len(notes.cards) == 1


async def test_nothing_backed_is_not_covered_not_a_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The passages not supporting the topic is an answer, not an error."""
    _stub_reply(monkeypatch, _payload(_card(sources="[9]")))

    with pytest.raises(TopicNotCovered):
        await generate_topic_notes(
            topic="Quantum chromodynamics", passages=_passages()
        )


async def test_malformed_json_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_reply(monkeypatch, '{"title": "Cut off", "cards": [')

    with pytest.raises(TopicNotesError):
        await generate_topic_notes(topic="B-trees", passages=_passages())


async def test_a_truncated_reply_is_reported_as_truncated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A cut-off reply needs different advice from a garbled one."""
    _stub_reply(monkeypatch, '{"title": "Cut off", "cards": [', finish_reason="length")

    with pytest.raises(TopicNotesTruncated):
        await generate_topic_notes(topic="B-trees", passages=_passages())


async def test_the_output_budget_is_sent(monkeypatch: pytest.MonkeyPatch) -> None:
    """The provider's default cap is what truncated a live run."""
    captured: dict[str, object] = {}

    async def fake(**kwargs):
        captured.update(kwargs)
        return _Response(_payload(_card()), "stop")

    monkeypatch.setattr(note_topic, "void_acompletion", fake)

    await generate_topic_notes(topic="B-trees", passages=_passages())

    assert captured["max_tokens"] == settings.notes_topic_max_tokens


async def test_a_wrong_shape_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_reply(monkeypatch, '{"title": "B-trees", "cards": "not a list"}')

    with pytest.raises(TopicNotesError):
        await generate_topic_notes(topic="B-trees", passages=_passages())


async def test_no_passages_raises_without_calling_the_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def explode(**kwargs):
        raise AssertionError("the model must not be called with no passages")

    monkeypatch.setattr(note_topic, "void_acompletion", explode)

    with pytest.raises(TopicNotesError):
        await generate_topic_notes(topic="B-trees", passages=[])


async def test_at_most_the_card_limit_is_kept(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cards = ", ".join(
        _card(concept=f"Concept {index}") for index in range(MAX_CARDS + 3)
    )
    _stub_reply(monkeypatch, _payload(cards))

    notes = await generate_topic_notes(topic="Trees", passages=_passages())

    assert len(notes.cards) == MAX_CARDS


def test_the_prompt_numbers_each_passage() -> None:
    prompt = build_user_prompt("B-trees", _passages())

    assert "[1] (Storage engines > B-trees, pp. 99-103)" in prompt
    assert "[2] (Storage engines > LSM-trees, pp. 104-108)" in prompt
    assert "B-trees keep keys sorted inside fixed-size pages." in prompt


def test_a_single_page_passage_is_labelled_p() -> None:
    passage = TopicPassage(
        number=1, heading_path="Cover", page_start=1, page_end=1, text="x"
    )

    assert "(Cover, p. 1)" in build_user_prompt("anything", [passage])
