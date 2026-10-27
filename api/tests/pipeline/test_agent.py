"""BookAgent tests (plan unit U11, revised).

The agent's job is the routing decision: greet, decline, or retrieve. The final
grounded answer is `qa_chain.answer_question_stream`, which is stubbed here so
these tests make no model calls.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import httpx
import pytest

from app.core.config import settings
from app.pipeline import agent as agent_module
from app.pipeline.agent import SEARCH_TOOL, BookAgent


def _message(content: str = "", tool_calls=None):
    return SimpleNamespace(content=content, tool_calls=tool_calls or [])


def _tool_call(query: str, call_id: str = "call-1", raw: str | None = None):
    arguments = raw if raw is not None else json.dumps({"query": query})
    return SimpleNamespace(
        id=call_id,
        function=SimpleNamespace(name="search_book", arguments=arguments),
    )


def _response(message):
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


class _Completer:
    """Returns queued responses and records the calls it received.

    Once the queue is empty it keeps answering with a plain message, so a test
    only has to script the rounds it actually cares about.
    """

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls: list[dict] = []

    async def __call__(self, **kwargs):
        self.calls.append(kwargs)
        if not self.responses:
            return _response(_message(""))
        return self.responses.pop(0)


class _Search:
    def __init__(self, passages=None):
        self.queries: list[str] = []
        self._passages = passages if passages is not None else [object()]

    async def __call__(self, query: str):
        self.queries.append(query)
        return list(self._passages)


@pytest.fixture(autouse=True)
def stub_grounded_answer(monkeypatch: pytest.MonkeyPatch):
    """Replace the streaming grounded answer; record the context it was given."""
    captured: dict = {}

    async def fake_answer(*, question, context, summary, history):
        captured["question"] = question
        captured["context"] = context
        yield json.dumps({"type": "token", "text": "Grounded answer."}).encode() + b"\n"

    monkeypatch.setattr(agent_module, "answer_question_stream", fake_answer)
    return captured


def _agent(completer, search, compose=lambda found: "COMPOSED CONTEXT"):
    return BookAgent(
        book_title="Test Book",
        search=search,
        compose=compose,
        completer=completer,
    )


async def _collect(agent, question, **kwargs):
    return [event async for event in agent.stream(question, **kwargs)]


# --------------------------------------------------------------------------
# Greetings and off-topic: no retrieval
# --------------------------------------------------------------------------


async def test_a_greeting_does_not_retrieve() -> None:
    completer = _Completer([_response(_message("Hello! Ask me about the book."))])
    search = _Search()

    agent = _agent(completer, search)
    events = await _collect(agent, "hi there")

    assert search.queries == []
    assert agent.passages == []
    assert events == [{"type": "token", "text": "Hello! Ask me about the book."}]


async def test_the_greeting_path_costs_one_model_call() -> None:
    completer = _Completer([_response(_message("Hi!"))])
    agent = _agent(completer, _Search())

    await _collect(agent, "hello")

    assert len(completer.calls) == 1


async def test_an_empty_decision_searches_instead_of_declining(
    stub_grounded_answer,
) -> None:
    """A blank decision is a malfunction, not a refusal."""
    completer = _Completer([_response(_message(""))])
    search = _Search()
    agent = _agent(completer, search)

    events = await _collect(agent, "something odd")

    assert search.queries == ["something odd"]
    assert events == [{"type": "token", "text": "Grounded answer."}]


async def test_the_canned_reply_only_appears_when_nothing_is_retrieved() -> None:
    completer = _Completer([_response(_message(""))])
    agent = _agent(completer, _Search(passages=[]))

    events = await _collect(agent, "something odd")

    assert len(events) == 1
    assert "only answer questions about this book" in events[0]["text"]


# --------------------------------------------------------------------------
# Book questions: retrieve, then answer from the passages
# --------------------------------------------------------------------------


async def test_a_book_question_calls_the_search_tool(stub_grounded_answer) -> None:
    completer = _Completer(
        [
            _response(_message("", [_tool_call("b-trees")])),
            _response(_message("Answering now.")),
        ]
    )
    search = _Search()
    agent = _agent(completer, search)

    events = await _collect(agent, "what is a b-tree")

    assert search.queries == ["b-trees"]
    assert events == [{"type": "token", "text": "Grounded answer."}]


async def test_the_retrieved_passages_reach_the_answer_context(
    stub_grounded_answer,
) -> None:
    completer = _Completer([_response(_message("", [_tool_call("b-trees")]))])
    agent = _agent(completer, _Search())

    await _collect(agent, "what is a b-tree")

    assert stub_grounded_answer["context"] == "COMPOSED CONTEXT"


async def test_the_decision_text_is_discarded_when_retrieval_happened() -> None:
    """The grounded answer is the answer; the routing text is not."""
    completer = _Completer(
        [_response(_message("I should look this up.", [_tool_call("b-trees")]))]
    )
    agent = _agent(completer, _Search())

    events = await _collect(agent, "what is a b-tree")

    assert [event["text"] for event in events] == ["Grounded answer."]


async def test_the_agent_is_given_the_search_tool() -> None:
    completer = _Completer([_response(_message("Hi!"))])
    agent = _agent(completer, _Search())

    await _collect(agent, "hello")

    assert completer.calls[0]["tools"] == [SEARCH_TOOL]
    assert completer.calls[0]["tool_choice"] == "auto"


# --------------------------------------------------------------------------
# Query handling
# --------------------------------------------------------------------------


async def test_a_failed_decision_falls_back_to_a_direct_search(
    stub_grounded_answer,
) -> None:
    """A hung or broken routing call must not cost the student their answer."""

    class _Broken:
        async def __call__(self, **kwargs):
            raise httpx.ReadTimeout("")

    search = _Search()
    agent = BookAgent(
        book_title="T",
        search=search,
        compose=lambda found: "COMPOSED CONTEXT",
        completer=_Broken(),
    )

    events = await _collect(agent, "what is a b-tree")

    assert search.queries == ["what is a b-tree"], "searches with the raw question"
    assert agent.passages, "and still answers from what came back"
    assert events == [{"type": "token", "text": "Grounded answer."}]


async def test_a_failed_decision_with_no_results_still_answers() -> None:
    class _Broken:
        async def __call__(self, **kwargs):
            raise httpx.ReadTimeout("")

    agent = BookAgent(
        book_title="T",
        search=_Search(passages=[]),
        compose=lambda found: "CTX",
        completer=_Broken(),
    )

    events = await _collect(agent, "hello")

    assert len(events) == 1
    assert events[0]["type"] == "token"


async def test_malformed_tool_arguments_fall_back_to_the_question() -> None:
    completer = _Completer(
        [_response(_message("", [_tool_call("", raw="not json")]))]
    )
    search = _Search()
    agent = _agent(completer, search)

    await _collect(agent, "what is a b-tree")

    assert search.queries == ["what is a b-tree"]


async def test_an_empty_query_falls_back_to_the_question() -> None:
    completer = _Completer([_response(_message("", [_tool_call("   ")]))])
    search = _Search()
    agent = _agent(completer, search)

    await _collect(agent, "what is a b-tree")

    assert search.queries == ["what is a b-tree"]


async def test_a_repeated_query_is_not_searched_twice(
    stub_grounded_answer,
) -> None:
    """Two rounds with the same query must not double the prompt."""
    completer = _Completer(
        [
            _response(_message("", [_tool_call("b-trees", "c1")])),
            _response(_message("", [_tool_call("b-trees", "c2")])),
        ]
    )
    search = _Search()
    agent = _agent(completer, search)
    agent.max_searches = 3

    await _collect(agent, "what is a b-tree")

    assert search.queries == ["b-trees"], "the duplicate must be skipped"
    assert len(agent.passages) == 1


async def test_searches_are_bounded_by_the_setting() -> None:
    tool_call = _tool_call("b-trees")
    completer = _Completer(
        [_response(_message("", [tool_call])) for _ in range(5)]
    )
    search = _Search()
    agent = _agent(completer, search)
    agent.max_searches = 1

    await _collect(agent, "what is a b-tree")

    assert search.queries == ["b-trees"]


async def test_multiple_searches_accumulate_passages(stub_grounded_answer) -> None:
    first, second = object(), object()
    searches = [
        _response(_message("", [_tool_call("first", "c1")])),
        _response(_message("", [_tool_call("second", "c2")])),
    ]
    completer = _Completer(searches)

    class _TwoSearches:
        def __init__(self):
            self.queries = []

        async def __call__(self, query):
            self.queries.append(query)
            return [first] if query == "first" else [second]

    search = _TwoSearches()
    agent = _agent(completer, search)
    agent.max_searches = 2

    composed: list = []
    agent._compose = lambda found: composed.extend(found) or "CTX"

    await _collect(agent, "question")

    assert search.queries == ["first", "second"]
    assert composed == [first, second]


# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------


async def test_the_configured_model_is_used(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "qa_agent_model", "some-other-model")
    completer = _Completer([_response(_message("Hi!"))])
    agent = _agent(completer, _Search())

    await _collect(agent, "hello")

    assert completer.calls[0]["model"] == "some-other-model"


async def test_an_explicit_model_overrides_the_setting() -> None:
    completer = _Completer([_response(_message("Hi!"))])
    agent = BookAgent(
        book_title="T",
        search=_Search(),
        compose=lambda found: "CTX",
        model="explicit-model",
        completer=completer,
    )

    await _collect(agent, "hello")

    assert completer.calls[0]["model"] == "explicit-model"


async def test_the_book_title_is_in_the_system_prompt() -> None:
    completer = _Completer([_response(_message("Hi!"))])
    agent = BookAgent(
        book_title="Designing Data-Intensive Applications",
        search=_Search(),
        compose=lambda found: "CTX",
        completer=completer,
    )

    await _collect(agent, "hello")

    system = completer.calls[0]["messages"][0]
    assert system["role"] == "system"
    assert "Designing Data-Intensive Applications" in system["content"]
