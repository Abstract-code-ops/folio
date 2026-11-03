"""Q&A streaming endpoint route handlers.

All endpoints are authenticated — Q&A messages are user-scoped data.
The current user is resolved from the session token at the router level.

Q&A is **book-scoped**. Two paths, chosen by ``settings.qa_agent_enabled``:

- **agent** (default): :class:`~app.pipeline.agent.BookAgent` decides whether the
  message needs the book at all. Greetings and off-topic messages are answered
  without retrieval, so they produce no citations and no coverage events.
- **legacy**: always retrieve the top-k chunks, then answer from them.

Both paths share the same grounded answer step, citation builder and
persistence, so the protected grounding prompt governs either way.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from typing import Any, AsyncGenerator

from fastapi import APIRouter, Depends, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.core.auth import get_current_user, get_optional_user
from app.core.config import settings
from app.core.db import AsyncSessionLocal
from app.core.ratelimit import rate_limit, rate_limit_by_ip
from app.models.book import Book
from app.models.coverage_event import CoverageEvent, EventType
from app.models.qa_message import QAMessage
from app.pipeline.agent import BookAgent
from app.pipeline.qa_chain import (
    answer_question_stream,
    build_context,
    summarize_conversation,
)
from app.services.qa import (
    ROLE_MATCH,
    ContextPassage,
    build_turn_diagnostics,
    build_used_citations,
    expand_context,
    list_recent_turns,
    retrieve_top_chunks,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/qa", tags=["qa"])


# ── Request schemas ────────────────────────────────────────────


class AskQuestionRequest(BaseModel):
    """Request body for ``POST /qa/{book_id}``."""

    question: str
    summary: str | None = None
    history: list[dict[str, str]] = []


class SummarizeRequest(BaseModel):
    """Request body for ``POST /qa/summarize``."""

    messages: list[dict[str, str]]


# ── Eval page schemas ──────────────────────────────────────────


class QaTurnResponse(BaseModel):
    """One recorded Q&A turn, as the eval page shows it."""

    id: uuid.UUID
    created_at: datetime
    book_id: uuid.UUID
    book_title: str | None = None
    question: str
    answer: str
    section_id: uuid.UUID | None = None
    sources: list[dict[str, Any]] | None = None
    diagnostics: dict[str, Any] | None = None


class QaTurnListResponse(BaseModel):
    """Newest-first list of turns."""

    turns: list[QaTurnResponse]
    total: int


# ── Endpoints ──────────────────────────────────────────────────


@router.post("/summarize")
async def summarize(
    body: SummarizeRequest,
    _rl: None = Depends(rate_limit_by_ip("qa_summarize", 20, 60)),
) -> dict[str, str]:
    """Summarise a conversation so later turns can carry a rolling summary."""
    if not body.messages:
        return {"summary": ""}
    summary = await summarize_conversation(body.messages)
    return {"summary": summary}


@router.get("/turns", response_model=QaTurnListResponse)
async def list_turns(
    response: Response,
    book_id: uuid.UUID | None = None,
    limit: int = 50,
    user_id: uuid.UUID = Depends(get_current_user),
) -> QaTurnListResponse:
    """Recent Q&A turns with their diagnostics, for the eval page.

    Declared before ``POST /{book_id}`` so the literal path is matched rather
    than captured as a book id. Scoped to the current user.
    """
    response.headers["Cache-Control"] = "private, max-age=10"
    async with AsyncSessionLocal() as db:
        rows = await list_recent_turns(
            db, user_id=user_id, book_id=book_id, limit=limit
        )
        turns = [
            QaTurnResponse(
                id=message.id,
                created_at=message.created_at,
                book_id=message.book_id,
                book_title=title,
                question=message.question,
                answer=message.answer,
                section_id=message.section_id,
                sources=message.sources,
                diagnostics=message.diagnostics,
            )
            for message, title in rows
        ]
    return QaTurnListResponse(turns=turns, total=len(turns))


@router.post("/{book_id}")
async def ask_question(
    book_id: uuid.UUID,
    body: AskQuestionRequest,
    _rl: None = Depends(rate_limit_by_ip("qa_ask", 40, 60)),
    user_id: uuid.UUID | None = Depends(get_optional_user),
) -> StreamingResponse:
    """Ask a question about the book, stream a grounded answer.

    The response is streamed as NDJSON with event types:
    - ``token`` — answer text fragments
    - ``citation`` — one per passage the answer actually cited, carrying the
      passage number, section heading, page range and an excerpt
    - ``not_covered`` — the book has no indexed content
    - ``done`` — end of stream marker with ``qa_message_id``
    """
    return StreamingResponse(
        _qa_stream(user_id, book_id, body.question, body.summary, body.history),
        media_type="application/x-ndjson",
        headers={
            "X-Accel-Buffering": "no",
            "Cache-Control": "no-cache",
        },
    )


# ── Streaming generator ────────────────────────────────────────


def _dedupe(passages: list[ContextPassage]) -> list[ContextPassage]:
    """Drop repeated passages, keeping first-seen order.

    The agent may search more than once; the same chunk can come back twice.
    """
    seen: set[tuple] = set()
    kept: list[ContextPassage] = []
    for passage in passages:
        key = (
            passage.role,
            passage.section.id,
            passage.chunk_index,
            passage.content[:64],
        )
        if key in seen:
            continue
        seen.add(key)
        kept.append(passage)
    return kept


def _matched_section_ids(passages: list[ContextPassage]) -> set[uuid.UUID]:
    """Sections that actually contributed a match, for coverage events."""
    return {
        passage.section.id
        for passage in passages
        if passage.role == ROLE_MATCH
    }


async def _qa_stream(
    user_id: uuid.UUID | None,
    book_id: uuid.UUID,
    question: str,
    summary: str | None = None,
    history: list[dict[str, str]] | None = None,
) -> AsyncGenerator[bytes, None]:
    """Async generator: decide → retrieve → stream answer → cite → persist."""
    full_answer: str = ""
    passages: list[ContextPassage] = []
    queries: list[str] = []
    stream_error: str | None = None
    reasoning_text: str = ""
    ttft_ms: int | None = None
    total_ms: int | None = None
    qa_mode = "agent" if settings.qa_agent_enabled else "legacy"

    async with AsyncSessionLocal() as db:
        try:
            if settings.qa_agent_enabled:
                book = await db.get(Book, book_id)
                if book is None:
                    yield json.dumps({
                        "type": "error",
                        "text": "This book is not available.",
                    }).encode() + b"\n"
                    return

                # Release the pooled connection before the (long) stream; the
                # search below opens its own short-lived sessions.
                await db.commit()

                async def search(query: str) -> list[ContextPassage]:
                    """Retrieval, injected into the agent so it stays layer-pure.

                    Uses its own session so the agent can run several searches
                    concurrently in one round.
                    """
                    async with AsyncSessionLocal() as search_db:
                        hits = await retrieve_top_chunks(search_db, book_id, query)
                        return await expand_context(search_db, hits)

                agent = BookAgent(
                    book_title=book.title,
                    search=search,
                    compose=lambda found: build_context(
                        [(passage, passage.distance or 0.0) for passage in found]
                    ),
                )
                async for event in agent.stream(
                    question, summary=summary, history=history
                ):
                    etype = event.get("type")
                    if etype == "reasoning":
                        reasoning_text = event.get("text") or ""
                        ttft_ms = event.get("ttft_ms")
                        total_ms = event.get("total_ms")
                        continue  # eval-only — not shown in the chat
                    if etype == "token":
                        full_answer += event.get("text", "")
                    if etype == "error":
                        stream_error = event.get("text")
                    yield json.dumps(event).encode() + b"\n"
                queries = list(agent.queries)
                passages = _dedupe(agent.passages)

            else:
                # Legacy path: always retrieve, then answer from the passages.
                hits = await retrieve_top_chunks(db, book_id, question)
                if not hits:
                    yield json.dumps({
                        "type": "not_covered",
                        "text": "This book has no indexed content for Q&A.",
                    }).encode() + b"\n"
                    return
                passages = await expand_context(db, hits)
                context = build_context(
                    [(passage, passage.distance or 0.0) for passage in passages]
                )
                # Release the pooled connection before the (long) stream.
                await db.commit()
                async for event_bytes in answer_question_stream(
                    question=question,
                    context=context,
                    summary=summary,
                    history=history,
                ):
                    event = json.loads(event_bytes)
                    if event.get("type") == "reasoning":
                        reasoning_text = event.get("text") or ""
                        ttft_ms = event.get("ttft_ms")
                        total_ms = event.get("total_ms")
                        continue
                    if event.get("type") == "token":
                        full_answer += event.get("text", "")
                    if event.get("type") == "error":
                        stream_error = event.get("text")
                    yield event_bytes

            # Citations for the passages the answer actually cited. A greeting
            # or an off-topic reply retrieves nothing, so it cites nothing.
            citations = build_used_citations(full_answer, passages) if passages else []
            for citation in citations:
                yield json.dumps(citation).encode() + b"\n"

            # Anonymous guests get a trial answer with NO persistence — no
            # qa_message, no coverage event; their history is client-side only.
            if user_id is None:
                yield json.dumps({"type": "done", "guest": True}).encode() + b"\n"
            else:
                matched_ids = _matched_section_ids(passages)
                diagnostics = build_turn_diagnostics(
                    mode=qa_mode,
                    queries=queries,
                    passages=passages,
                    citation_count=len(citations),
                    answer_chars=len(full_answer),
                    reasoning=reasoning_text,
                    ttft_ms=ttft_ms,
                    total_ms=total_ms,
                    error=stream_error,
                )
                qa_message = QAMessage(
                    user_id=user_id,
                    book_id=book_id,
                    section_id=next(iter(matched_ids), None),
                    question=question,
                    answer=full_answer,
                    sources=citations if citations else None,
                    diagnostics=diagnostics,
                )
                db.add(qa_message)
                await db.flush()
                for sid in matched_ids:
                    db.add(
                        CoverageEvent(
                            user_id=user_id,
                            book_id=book_id,
                            section_id=sid,
                            event_type=EventType.QA_ASKED,
                            event_metadata={"qa_message_id": str(qa_message.id)},
                        )
                    )
                await db.commit()
                yield json.dumps({
                    "type": "done",
                    "qa_message_id": str(qa_message.id),
                }).encode() + b"\n"

        except Exception as e:
            await db.rollback()
            logger.exception("Q&A stream failed for book %s", book_id)
            detail = str(e).strip() or type(e).__name__
            yield json.dumps({
                "type": "error",
                "text": f"Q&A failed: {detail}",
            }).encode() + b"\n"
