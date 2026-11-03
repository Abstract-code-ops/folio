"""Conversational gate in front of retrieval (plan unit U11, revised).

The original U11 plan asked for a question rewriter: turn history plus the latest
message into a standalone question before retrieving. The curator replaced that.
Instead of rewriting, an **agent** looks at the message and decides whether the
book is needed at all, calling a search tool when it is.

That covers what rewriting was for, and more:

- a greeting or small talk gets a short reply and never touches the index, so it
  costs no retrieval and produces no citations or coverage events;
- an off-topic question is declined instead of being answered from irrelevant
  passages;
- a real question calls ``search_book``, and the answer is generated from the
  retrieved passages exactly as before.

Layering: this module orchestrates model calls only. Retrieval and context
composition are injected as callbacks, so nothing here imports services, the
database, or the models package. The final answer still goes through the
grounded prompt in :mod:`app.pipeline.qa_chain`, which keeps the protected
invariant and the existing citation discipline intact.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from collections.abc import AsyncGenerator, Awaitable, Callable, Sequence
from typing import Any, Optional

import httpx

from app.core.config import settings
from app.core.llm import void_acompletion
from app.pipeline.qa_chain import answer_question_stream

logger = logging.getLogger(__name__)

# Routing is a classification step, not generation. If it has not answered in
# this long the provider is unhealthy, and waiting the full generation timeout
# would leave the student staring at a blank panel.
_DECISION_TIMEOUT = httpx.Timeout(connect=10.0, read=20.0, write=15.0, pool=10.0)
# Injected by the caller: query -> passages, and passages -> context string.
SearchFn = Callable[[str], Awaitable[Sequence[Any]]]
ComposeFn = Callable[[Sequence[Any]], str]
# Injected by tests: keyword-compatible stand-in for void_acompletion.
Completer = Callable[..., Awaitable[Any]]

SEARCH_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "search_book",
        "description": (
            "Search the textbook for passages relevant to a query. Call this "
            "whenever the student asks something this book might cover."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "Short search query, phrased in the book's own "
                        "vocabulary where possible."
                    ),
                }
            },
            "required": ["query"],
        },
    },
}

AGENT_SYSTEM_PROMPT = """You are the routing step of a study assistant for the book "{title}".

Decide what the student's message needs, then act:

- Greeting, thanks, or small talk: reply briefly and warmly in one or two sentences and invite a question about the book. Do NOT call search_book.
- A question this book might answer: call search_book with a short, specific query, spelled the way the book would spell it. Never answer a book question from memory.
- If two or more searches would help (e.g. related sub-topics, or a broad term plus a specific one), issue them together in the SAME response so they run in parallel — do not search, read, then search again.
- Only if the message is obviously unrelated to this book (weather, sport, other books, general trivia): say briefly that you only cover this book. Do NOT call search_book.

Misspellings, typos, abbreviations and half-remembered terms are NOT off-topic. Work out what the student meant, fix the spelling in your query, and search. For example "as tables instd of ss tables" is a misspelled request about SSTables: search for "SSTable", do not decline it.

Declining is a last resort. If there is any chance the book covers the topic, call search_book and let the passages decide. Never invent content.

Output nothing at all only if you cannot decide — the caller will search on its own in that case."""


def _tool_call_message(message: Any, calls: Sequence[Any]) -> dict[str, Any]:
    """Rebuild an assistant tool-call turn as a plain dict for the next request."""
    return {
        "role": "assistant",
        "content": getattr(message, "content", "") or "",
        "tool_calls": [
            {
                "id": call.id,
                "type": "function",
                "function": {
                    "name": call.function.name,
                    "arguments": call.function.arguments,
                },
            }
            for call in calls
        ],
    }


def _query_from(call: Any, fallback: str) -> str:
    """Pull the query out of a tool call, tolerating malformed arguments."""
    try:
        arguments = json.loads(call.function.arguments or "{}")
    except (json.JSONDecodeError, TypeError):
        return fallback
    query = arguments.get("query")
    return query.strip() if isinstance(query, str) and query.strip() else fallback


class BookAgent:
    """Decides whether a message needs the book, then answers it.

    Usage::

        agent = BookAgent(book_title=..., search=..., compose=...)
        async for event in agent.stream(question, history=history):
            ...  # emit event as NDJSON

    After streaming, ``agent.passages`` holds everything retrieval returned, so
    the caller can build citations from the passages the answer really used.
    """

    def __init__(
        self,
        *,
        book_title: str,
        search: SearchFn,
        compose: ComposeFn,
        model: Optional[str] = None,
        max_searches: Optional[int] = None,
        temperature: Optional[float] = None,
        completer: Optional[Completer] = None,
    ) -> None:
        self.book_title = book_title
        self.model = model or settings.qa_agent_model
        self.max_searches = (
            max_searches if max_searches is not None else settings.qa_agent_max_searches
        )
        self.temperature = (
            temperature
            if temperature is not None
            else settings.qa_agent_temperature
        )
        self._search = search
        self._compose = compose
        self._completer = completer or void_acompletion

        # Filled in while streaming.
        self.queries: list[str] = []
        self.passages: list[Any] = []

    # ── Message assembly ──────────────────────────────────────

    def _messages(
        self,
        question: str,
        summary: Optional[str],
        history: Optional[list[dict[str, str]]],
    ) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": AGENT_SYSTEM_PROMPT.format(title=self.book_title),
            }
        ]
        if summary:
            messages.append(
                {"role": "system", "content": f"Earlier in this conversation: {summary}"}
            )
        for turn in history or []:
            content = (turn.get("content") or "").strip()
            if not content:
                continue
            role = "assistant" if turn.get("role") == "assistant" else "user"
            messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": question})
        return messages

    # ── Decision loop ─────────────────────────────────────────

    async def _decide(
        self, messages: list[dict[str, Any]]
    ) -> Optional[str]:
        """Run the tool-calling loop. Returns the decision text when no search ran."""
        decision_text: Optional[str] = None

        for _round in range(self.max_searches + 1):
            response = await self._completer(
                model=self.model,
                messages=messages,
                tools=[SEARCH_TOOL],
                tool_choice="auto",
                temperature=self.temperature,
                reasoning_effort=settings.qa_reasoning_effort,
                timeout=_DECISION_TIMEOUT,
            )
            message = response.choices[0].message
            calls = list(getattr(message, "tool_calls", None) or [])
            decision_text = getattr(message, "content", None) or ""

            if not calls:
                return decision_text

            messages.append(_tool_call_message(message, calls))

            # Plan this round's new, unique, in-budget queries first, so a round
            # that asks for several can be retrieved concurrently.
            plan: list[tuple[Any, str]] = []
            over_budget = False
            for call in calls:
                if len(self.queries) + len(plan) >= self.max_searches:
                    over_budget = True
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call.id,
                            "content": (
                                "Search limit reached; answer from the results "
                                "already retrieved."
                            ),
                        }
                    )
                    continue
                query = _query_from(call, messages[-2]["content"])
                if query in self.queries or any(query == q for _, q in plan):
                    # Re-searching the identical query doubles the context for
                    # no new information; a second round is for refining.
                    logger.info("Agent repeated %r; not searching again", query)
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call.id,
                            "content": "Already searched for that; results are attached.",
                        }
                    )
                    continue
                plan.append((call, query))

            async def _run(query: str) -> list[Any]:
                return list(await self._search(query) or [])

            results = (
                await asyncio.gather(*(_run(query) for _, query in plan))
                if plan
                else []
            )
            for (call, query), found in zip(plan, results):
                self.queries.append(query)
                self.passages.extend(found)
                logger.info("Agent searched %r -> %d passage(s)", query, len(found))
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": (
                            f"{len(found)} passage(s) retrieved and attached to "
                            "the answer context."
                        ),
                    }
                )

            if over_budget:
                return None

        return None

    # ── Public API ────────────────────────────────────────────

    async def _search_directly(self, question: str) -> None:
        """Retrieve without a routing decision — the pre-agent behaviour.

        Used when routing fails or returns nothing, so a broken or confused
        router cannot cost the student their answer.
        """
        found = list(await self._search(question) or [])
        self.queries.append(question)
        self.passages.extend(found)

    def _rerank(self, question: str, matches: list[Any]) -> list[Any]:
        """Reorder candidate matches by relevance to the question.

        Lightweight hybrid: lower embedding distance is better, plus a lexical
        overlap bonus for passages that actually contain the question's terms.
        Dependency-free; a cross-encoder can replace this body later.
        """
        if not settings.rerank_enabled or len(matches) <= 1:
            return sorted(
                matches,
                key=lambda p: getattr(p, "distance", None)
                if getattr(p, "distance", None) is not None
                else float("inf"),
            )

        terms = {w for w in re.findall(r"[a-z0-9]+", question.lower()) if len(w) > 2}

        def score(passage: Any) -> float:
            content = (getattr(passage, "content", "") or "").lower()
            overlap = (
                sum(1 for term in terms if term in content) / max(1, len(terms))
            )
            distance = getattr(passage, "distance", None)
            distance = distance if distance is not None else 1.0
            return overlap - distance

        return sorted(matches, key=score, reverse=True)

    def _answer_passages(self, question: str) -> list[Any]:
        """Dedupe the accumulated passages and cap what the answer is built from.

        Several searches can return overlapping passages. Composing all of them
        inflates the prompt (and the provider-failure surface) without adding
        information, so keep the best ``retrieval_top_k`` matches by distance,
        plus up to that many context passages (neighbours / parent summaries).
        The result is also assigned back to ``self.passages`` so the citation
        numbers in the answer line up with exactly what was sent.
        """
        limit = max(1, settings.retrieval_top_k)

        def key_of(passage: Any) -> tuple:
            section_id = getattr(getattr(passage, "section", None), "id", None)
            chunk_index = getattr(passage, "chunk_index", None)
            if section_id is None and chunk_index is None:
                return ("obj", id(passage))
            return (section_id, chunk_index)

        matches: dict[tuple, Any] = {}
        contexts: list[tuple[tuple, Any]] = []

        for passage in self.passages:
            key = key_of(passage)
            if getattr(passage, "role", "match") == "match":
                distance = getattr(passage, "distance", None)
                distance = distance if distance is not None else float("inf")
                prev = matches.get(key)
                prev_distance = getattr(prev, "distance", None)
                if prev is None or distance < (
                    prev_distance if prev_distance is not None else float("inf")
                ):
                    matches[key] = passage
            else:
                contexts.append((key, passage))

        ordered = self._rerank(question, list(matches.values()))
        kept = ordered[:limit]

        kept_keys = {key_of(p) for p in kept}
        seen: set[tuple] = set()
        for key, passage in contexts:
            if key in kept_keys or key in seen:
                continue
            seen.add(key)
            kept.append(passage)
            if len(seen) >= limit:
                break

        return kept

    async def stream(
        self,
        question: str,
        *,
        summary: Optional[str] = None,
        history: Optional[list[dict[str, str]]] = None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Yield answer events. Retrieval happens only if the agent asks for it."""
        messages = self._messages(question, summary, history)

        try:
            decision_text = await self._decide(messages)
        except Exception as exc:  # noqa: BLE001 - routing must not kill the turn
            # The routing call is the only step here that is not already
            # protected downstream. If it hangs or the provider errors, fall
            # back to the pre-agent behaviour: search with the question itself
            # and answer from what comes back.
            logger.warning(
                "Agent decision failed (%s: %s); falling back to a direct search",
                type(exc).__name__,
                exc,
            )
            decision_text = None
            if not self.passages:
                await self._search_directly(question)

        # A blank decision is a malfunction, not a refusal. Treat it like a
        # routing failure: the student asked something, so search for it rather
        # than answering with a canned decline.
        if not self.passages and not (decision_text or "").strip():
            logger.warning(
                "Agent returned an empty decision for %r; searching directly",
                question[:80],
            )
            await self._search_directly(question)

        if self.passages:
            self.passages = self._answer_passages(question)
            context = self._compose(self.passages)
            async for event_bytes in answer_question_stream(
                question=question,
                context=context,
                summary=summary,
                history=history,
            ):
                # Forward every event, not just tokens: the answer stream emits
                # an `error` event when the model degenerates or the provider
                # cuts it off, and the UI needs to see that.
                yield json.loads(event_bytes)
            return

        # No retrieval: a greeting or an off-topic decline. Nothing to ground.
        text = (decision_text or "").strip()
        if not text:
            text = (
                "I can only answer questions about this book. "
                "Ask me about a topic it covers."
            )
        yield {"type": "token", "text": text}
