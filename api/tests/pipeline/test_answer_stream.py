"""Answer-stream resilience tests.

The failure this protects against: gpt-oss-20b degenerated into repeating one
token until the provider killed the stream. Before this, that exception threw
away the partial answer, the citations, the persistence and the `done` event.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app.core.config import settings
from app.pipeline import qa_chain


def _delta(text: str):
    return SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=text))])


class _Stream:
    """Async iterator that yields deltas, then either stops or raises."""

    def __init__(self, deltas, exc: Exception | None = None):
        self._deltas = list(deltas)
        self._exc = exc

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._deltas:
            return _delta(self._deltas.pop(0))
        if self._exc is not None:
            raise self._exc
        raise StopAsyncIteration


def _patch(monkeypatch: pytest.MonkeyPatch, stream, captured: dict | None = None):
    async def fake(**kwargs):
        if captured is not None:
            captured.update(kwargs)
        return stream

    monkeypatch.setattr(qa_chain, "void_acompletion", fake)


async def _collect(context: str = "ctx") -> list[dict]:
    events = []
    async for raw in qa_chain.answer_question_stream(
        question="what is a shard?", context=context, summary=None, history=None
    ):
        event = json.loads(raw)
        # The "reasoning" event carries model timings/reasoning for the eval; it
        # is meta, not an answer event, so these assertions ignore it.
        if event.get("type") == "reasoning":
            continue
        events.append(event)
    return events


# --------------------------------------------------------------------------
# Happy path
# --------------------------------------------------------------------------


async def test_tokens_are_forwarded(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch(monkeypatch, _Stream(["A shard ", "is a partition."]))

    events = await _collect()

    assert [event["type"] for event in events] == ["token", "token"]
    assert events[0]["text"] == "A shard "


async def test_the_answer_length_is_capped(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}
    _patch(monkeypatch, _Stream(["text"]), captured)

    await _collect()

    assert captured["max_tokens"] == settings.qa_answer_max_tokens


# --------------------------------------------------------------------------
# Repetition loop
# --------------------------------------------------------------------------


async def test_a_repetition_loop_is_stopped(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch(monkeypatch, _Stream(["international "] * 200))

    events = await _collect()

    assert events[-1]["type"] == "error"
    assert "repeating itself" in events[-1]["text"]
    tokens = [event for event in events if event["type"] == "token"]
    assert len(tokens) < 60, "the loop must be cut short, not streamed to the cap"


async def test_a_normal_answer_is_not_mistaken_for_a_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    words = " ".join(f"word{i}" for i in range(60))
    _patch(monkeypatch, _Stream(words.split(" ")))

    events = await _collect()

    assert all(event["type"] == "token" for event in events)


async def test_short_repeats_do_not_trigger_the_guard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A handful of repeated words is normal prose, not degeneration.
    _patch(monkeypatch, _Stream(["very "] * 10 + ["good."]))

    events = await _collect()

    assert all(event["type"] == "token" for event in events)


# --------------------------------------------------------------------------
# Provider failure mid-stream
# --------------------------------------------------------------------------


async def test_a_mid_stream_failure_becomes_an_event_not_an_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch(
        monkeypatch,
        _Stream(
            ["A shard ", "is a partition"],
            exc=RuntimeError("provider aborted the stream: repeating chunk"),
        ),
    )

    events = await _collect()

    assert [event["type"] for event in events] == ["token", "token", "error"]
    assert "cut off" in events[-1]["text"]


async def test_the_partial_answer_survives_a_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch(
        monkeypatch,
        _Stream(["partial text "], exc=RuntimeError("boom")),
    )

    events = await _collect()

    tokens = "".join(e["text"] for e in events if e["type"] == "token")
    assert tokens == "partial text "


async def test_a_failure_before_any_token_still_yields_an_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch(monkeypatch, _Stream([], exc=RuntimeError("boom")))

    events = await _collect()

    assert [event["type"] for event in events] == ["error"]
    assert "did not respond" in events[-1]["text"]


async def test_a_failure_before_any_token_is_retried_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A provider that dies before sending anything is safe to retry."""
    streams = [_Stream([], exc=RuntimeError("upstream error chunk")), _Stream(["Recovered."])]
    calls = {"n": 0}

    async def fake(**kwargs):
        stream = streams[min(calls["n"], len(streams) - 1)]
        calls["n"] += 1
        return stream

    monkeypatch.setattr(qa_chain, "void_acompletion", fake)

    events = await _collect()

    assert [event["type"] for event in events] == ["token"]
    assert events[0]["text"] == "Recovered."
    assert calls["n"] == 2


async def test_a_failure_after_tokens_is_not_retried(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Retrying would interleave two partial answers, so it must not happen."""
    calls = {"n": 0}

    async def fake(**kwargs):
        calls["n"] += 1
        return _Stream(["partial "], exc=RuntimeError("boom"))

    monkeypatch.setattr(qa_chain, "void_acompletion", fake)

    events = await _collect()

    assert [event["type"] for event in events] == ["token", "error"]
    assert "cut off" in events[-1]["text"]
    assert calls["n"] == 1


async def test_two_failures_before_any_token_report_the_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = {"n": 0}

    async def fake(**kwargs):
        calls["n"] += 1
        return _Stream([], exc=RuntimeError("boom"))

    monkeypatch.setattr(qa_chain, "void_acompletion", fake)

    events = await _collect()

    assert [event["type"] for event in events] == ["error"]
    assert calls["n"] == 2, "one retry, not an unbounded loop"


# --------------------------------------------------------------------------
# The guard itself
# --------------------------------------------------------------------------


def test_degenerate_detects_a_sustained_repeat() -> None:
    assert qa_chain._is_degenerate(["international "] * 30) is True


def test_degenerate_ignores_short_input() -> None:
    assert qa_chain._is_degenerate(["international "] * 5) is False


def test_degenerate_ignores_varied_text() -> None:
    assert qa_chain._is_degenerate(["alpha beta gamma "] * 30) is False
