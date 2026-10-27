"""Tests for note-generation output handling (plan unit U3).

The old code did a bare ``json.loads`` and indexed ``parsed["concepts"]``,
so a truncated or off-schema reply surfaced as a ``JSONDecodeError`` or a
``KeyError`` from deep inside the pipeline. These tests pin the contract:
whatever the model returns, the caller sees ``NoteGenerationError`` or a
validated ``GeneratedSectionNotes``.
"""

from __future__ import annotations

import logging

import pytest

from app.pipeline import note_gen
from app.pipeline.note_gen import (
    MAX_INPUT_WORDS,
    GeneratedSectionNotes,
    NoteGenerationError,
    generate_section_notes,
)


class _Message:
    def __init__(self, content: str) -> None:
        self.content = content


class _Choice:
    def __init__(self, content: str, finish_reason: str) -> None:
        self.message = _Message(content)
        self.finish_reason = finish_reason


class _Response:
    def __init__(self, content: str, finish_reason: str = "stop") -> None:
        self.choices = [_Choice(content, finish_reason)]


def _stub_completion(monkeypatch: pytest.MonkeyPatch, content: str, finish_reason: str = "stop") -> None:
    async def fake(**kwargs):
        return _Response(content, finish_reason)

    monkeypatch.setattr(note_gen, "void_acompletion", fake)


ONE_CONCEPT = (
    '{"concepts": [{"name": "B-tree", "definition": "A balanced tree", '
    '"explanation": "It keeps keys sorted.", "example": "from the text", '
    '"self_check": "Why is it balanced?"}]}'
)


async def _generate() -> GeneratedSectionNotes:
    return await generate_section_notes(
        section_id="section-1",
        heading="B-trees",
        raw_text="A B-tree keeps its keys sorted.",
        page_start=99,
        page_end=103,
        metadata={"summary": "About B-trees."},
    )


# --------------------------------------------------------------------------
# Happy path
# --------------------------------------------------------------------------


async def test_valid_output_is_validated_into_the_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_completion(monkeypatch, ONE_CONCEPT)

    notes = await _generate()

    assert isinstance(notes, GeneratedSectionNotes)
    assert notes.section_id == "section-1"
    assert notes.section_heading == "B-trees"
    assert notes.page_start == 99
    assert notes.page_end == 103
    assert len(notes.concepts) == 1
    assert notes.concepts[0].name == "B-tree"


async def test_a_markdown_code_fence_is_tolerated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_completion(monkeypatch, f"```json\n{ONE_CONCEPT}\n```")

    notes = await _generate()

    assert len(notes.concepts) == 1


# --------------------------------------------------------------------------
# Malformed output never escapes as JSONDecodeError or KeyError
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("content", "finish_reason"),
    [
        ('{"concepts": [{"name": "cut off mid', "stop"),
        ("not json at all", "stop"),
        ("", "stop"),
        ("   ", "stop"),
        ('{"concepts": [{"name": "unterminated"', "length"),
    ],
)
async def test_malformed_output_raises_note_generation_error(
    monkeypatch: pytest.MonkeyPatch,
    content: str,
    finish_reason: str,
) -> None:
    _stub_completion(monkeypatch, content, finish_reason)

    with pytest.raises(NoteGenerationError):
        await _generate()


async def test_truncated_output_says_it_was_truncated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_completion(
        monkeypatch,
        '{"concepts": [{"name": "cut off',
        finish_reason="length",
    )

    with pytest.raises(NoteGenerationError):
        await _generate()


async def test_missing_concepts_key_raises_note_generation_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """This used to be a KeyError from `parsed["concepts"]`."""
    _stub_completion(monkeypatch, '{"something_else": []}')

    with pytest.raises(NoteGenerationError):
        await _generate()


async def test_a_concept_missing_a_field_raises_note_generation_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_completion(
        monkeypatch,
        '{"concepts": [{"name": "B-tree", "definition": "A balanced tree"}]}',
    )

    with pytest.raises(NoteGenerationError):
        await _generate()


async def test_a_json_array_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_completion(monkeypatch, '[{"name": "B-tree"}]')

    with pytest.raises(NoteGenerationError):
        await _generate()


# --------------------------------------------------------------------------
# Input cap
# --------------------------------------------------------------------------


def test_overlong_section_is_truncated_and_logged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    overlong = "word " * (MAX_INPUT_WORDS + 500)

    with caplog.at_level(logging.WARNING, logger=note_gen.__name__):
        result = note_gen._truncate_for_prompt("Huge Heading", overlong)

    assert len(result.split()) == MAX_INPUT_WORDS
    messages = [record.getMessage() for record in caplog.records]
    assert any("Truncating section" in message for message in messages)


def test_section_under_the_cap_is_untouched() -> None:
    short = "short section text " * 10

    assert note_gen._truncate_for_prompt("Heading", short) == short


async def test_the_prompt_carries_the_truncated_text() -> None:
    overlong = "word " * (MAX_INPUT_WORDS + 100)
    prompt = note_gen._build_user_prompt(
        "Heading", overlong, {"summary": "A summary."}
    )

    body = prompt.split("## Full Text", 1)[1].split("## Section Metadata", 1)[0]
    assert len(body.split()) == MAX_INPUT_WORDS
