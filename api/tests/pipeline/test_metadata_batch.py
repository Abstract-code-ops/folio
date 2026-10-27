"""Tests for metadata completeness and repair (plan unit U2).

The failure being fixed: a batch that comes back short used to fill the
missing sections with an empty metadata dict, so those sections ended with
no summary and no trace. These tests drive `extract_metadata_batch` with a
mocked model client and assert that dropped sections are re-requested and
that nothing ends silently empty.
"""

from __future__ import annotations

import logging

import pytest

from app.core.config import settings
from app.pipeline import metadata


@pytest.fixture(autouse=True)
def fast_metadata_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Shrink batches and remove inter-batch sleeps for the tests."""
    monkeypatch.setattr(settings, "gemini_metadata_batch_size", 3)
    monkeypatch.setattr(settings, "gemini_metadata_repair_attempts", 2)
    monkeypatch.setattr(settings, "gemini_batch_delay_seconds", 0)


def _sections(count: int) -> list[tuple[str, str]]:
    return [(f"Heading {i}", f"body text for section {i} " * 3) for i in range(count)]


def _answered(
    indices: list[int], summary: str = "A real summary."
) -> dict[str, object]:
    """Build a model response answering the given positions in a batch."""
    return {
        "sections": [
            {
                "section_index": index,
                "learning_objectives": [],
                "summary": summary,
                "concepts": [f"concept-{index}"],
                "definitions": [],
                "equations": [],
                "examples": [],
                "exercise_count": 0,
            }
            for index in indices
        ]
    }


# --------------------------------------------------------------------------
# Repair: dropped sections come back
# --------------------------------------------------------------------------


async def test_sections_dropped_from_a_batch_are_rerequested(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A batch that answers only part of its sections triggers a repair pass."""
    calls: list[str] = []

    async def fake_call(system_prompt: str, user_prompt: str) -> dict:
        calls.append(user_prompt)
        if len(calls) == 1:
            # Batch of 3, but the model drops the third section.
            return _answered([0, 1])
        # Repair pass: whatever single section is asked for gets answered.
        return _answered([0])

    monkeypatch.setattr(metadata, "_call_gemini", fake_call)

    results = await metadata.extract_metadata_batch(_sections(3))

    assert len(calls) == 2, "the dropped section should trigger exactly one repair call"
    assert len(results) == 3
    assert all(result["status"] == metadata.METADATA_STATUS_OK for result in results)
    assert all(result["summary"] for result in results)


async def test_a_raising_batch_is_repaired_rather_than_discarded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A malformed or failed call marks its sections for repair, not for blank."""

    async def fake_call(system_prompt: str, user_prompt: str) -> dict:
        raise ValueError("model returned something that is not JSON")

    monkeypatch.setattr(metadata, "_call_gemini", fake_call)

    results = await metadata.extract_metadata_batch(
        _sections(3), batch_size=1
    )

    # Batch size 1 keeps the assertion about counts simple: every section
    # fails on its own, and every section ends explicitly failed.
    assert len(results) == 3
    assert all(
        result["status"] == metadata.METADATA_STATUS_FAILED for result in results
    )


# --------------------------------------------------------------------------
# Terminal states
# --------------------------------------------------------------------------


async def test_sections_never_answered_end_failed_with_a_log_line(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """No usable answer after every pass leaves an explicit failure, not a blank."""

    async def fake_call(system_prompt: str, user_prompt: str) -> dict:
        return {"sections": []}

    monkeypatch.setattr(metadata, "_call_gemini", fake_call)

    with caplog.at_level(logging.INFO, logger=metadata.__name__):
        results = await metadata.extract_metadata_batch(_sections(2))

    assert [result["status"] for result in results] == [
        metadata.METADATA_STATUS_FAILED,
        metadata.METADATA_STATUS_FAILED,
    ]
    messages = [record.getMessage() for record in caplog.records]
    assert any("Metadata failed" in message for message in messages), (
        "a failed section must produce a log line, never a silent empty result"
    )
    assert any("Metadata complete" in message for message in messages)


async def test_an_empty_summary_is_partial_and_not_rerequested(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Front matter has nothing to summarise; asking again would waste calls."""
    calls: list[str] = []

    async def fake_call(system_prompt: str, user_prompt: str) -> dict:
        calls.append(user_prompt)
        return _answered([0, 1, 2], summary="")

    monkeypatch.setattr(metadata, "_call_gemini", fake_call)

    results = await metadata.extract_metadata_batch(_sections(3))

    assert len(calls) == 1
    assert all(
        result["status"] == metadata.METADATA_STATUS_PARTIAL for result in results
    )


async def test_every_result_carries_a_status_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_call(system_prompt: str, user_prompt: str) -> dict:
        return _answered([0, 1, 2])

    monkeypatch.setattr(metadata, "_call_gemini", fake_call)

    results = await metadata.extract_metadata_batch(_sections(3))

    for result in results:
        assert "status" in result
        assert result["status"] in {
            metadata.METADATA_STATUS_OK,
            metadata.METADATA_STATUS_PARTIAL,
            metadata.METADATA_STATUS_FAILED,
        }
        assert set(result) == {
            "learning_objectives",
            "summary",
            "concepts",
            "definitions",
            "equations",
            "examples",
            "exercise_count",
            "status",
        }


# --------------------------------------------------------------------------
# Batching behaviour
# --------------------------------------------------------------------------


async def test_batches_follow_the_configured_size(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """7 sections at batch size 3 means three calls, not one or seven."""
    calls: list[str] = []

    async def fake_call(system_prompt: str, user_prompt: str) -> dict:
        calls.append(user_prompt)
        answered = user_prompt.count("--- Section ")
        return _answered(list(range(answered)))

    monkeypatch.setattr(metadata, "_call_gemini", fake_call)

    results = await metadata.extract_metadata_batch(_sections(7))

    assert len(calls) == 3
    assert all(result["status"] == metadata.METADATA_STATUS_OK for result in results)


async def test_repair_passes_are_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    """An unreachable model costs repair_attempts + 1 passes, then stops."""
    monkeypatch.setattr(settings, "gemini_metadata_repair_attempts", 1)
    calls: list[str] = []

    async def fake_call(system_prompt: str, user_prompt: str) -> dict:
        calls.append(user_prompt)
        return {"sections": []}

    monkeypatch.setattr(metadata, "_call_gemini", fake_call)

    results = await metadata.extract_metadata_batch(_sections(3))

    # Pass 1: one batch of 3. Pass 2 halves the batch size to 1, so the three
    # unanswered sections take three calls. That is 4 calls total and then the
    # loop stops - the point is that it terminates, not that it is cheap.
    assert len(calls) == 4
    assert all(
        result["status"] == metadata.METADATA_STATUS_FAILED for result in results
    )


async def test_out_of_range_section_indexes_are_ignored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A model that hallucinates an index must not blow up the batch."""

    async def fake_call(system_prompt: str, user_prompt: str) -> dict:
        return _answered([0, 99, -1])

    monkeypatch.setattr(metadata, "_call_gemini", fake_call)

    results = await metadata.extract_metadata_batch(_sections(1), batch_size=1)

    assert len(results) == 1
    assert results[0]["status"] == metadata.METADATA_STATUS_OK


async def test_empty_input_returns_empty_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_call(system_prompt: str, user_prompt: str) -> dict:
        raise AssertionError("should not be called for an empty input")

    monkeypatch.setattr(metadata, "_call_gemini", fake_call)

    assert await metadata.extract_metadata_batch([]) == []


# --------------------------------------------------------------------------
# Single-section path and JSON guard
# --------------------------------------------------------------------------


async def test_single_section_path_stamps_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_call(system_prompt: str, user_prompt: str) -> dict:
        return {"summary": "A one-line summary.", "concepts": ["x"]}

    monkeypatch.setattr(metadata, "_call_gemini", fake_call)

    result = await metadata.extract_metadata("Some heading", "some text")

    assert result["status"] == metadata.METADATA_STATUS_OK


async def test_single_section_with_empty_summary_is_partial(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_call(system_prompt: str, user_prompt: str) -> dict:
        return {"summary": ""}

    monkeypatch.setattr(metadata, "_call_gemini", fake_call)

    result = await metadata.extract_metadata("Cover", "")

    assert result["status"] == metadata.METADATA_STATUS_PARTIAL


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ('{"a": 1}', '{"a": 1}'),
        ('```json\n{"a": 1}\n```', '{"a": 1}'),
        ('```\n{"a": 1}\n```', '{"a": 1}'),
        ('  ```json\n{"a": 1}\n```  ', '{"a": 1}'),
    ],
)
def test_code_fences_are_stripped(raw: str, expected: str) -> None:
    assert metadata._strip_code_fence(raw) == expected


# --------------------------------------------------------------------------
# Transient-vs-permanent retry classification
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "message",
    [
        "429 Resource has been exhausted",
        "rate_limit exceeded",
        "500 INTERNAL",
        "503 UNAVAILABLE. This model is currently experiencing high demand.",
        "504 Deadline Exceeded",
        "The model is overloaded",
    ],
)
def test_transient_errors_are_retried(message: str) -> None:
    assert metadata._is_transient_error(RuntimeError(message)) is True


@pytest.mark.parametrize(
    "message",
    [
        "Invalid API key",
        "400 INVALID_ARGUMENT",
        "json decode failed",
    ],
)
def test_permanent_errors_are_not_retried(message: str) -> None:
    assert metadata._is_transient_error(RuntimeError(message)) is False
