"""Retrieval and grounded Q&A response generation.

The Q&A is scoped to a **book** — the pipeline searches all sections
of the book for relevant chunks, retrieves the top-k most similar,
and streams a grounded answer with per-section source citations.

Protected invariant: ``GROUNDING_SYSTEM_PROMPT`` is the Q&A grounding
system prompt. It is never overridden or appended to by user input.
Changes to it require an explicit code change and must be tested
against the out-of-scope question eval suite before deployment
(see docs/architecture.md).
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, AsyncGenerator

from app.core.config import settings
from app.core.llm import QA_MODEL, void_acompletion

logger = logging.getLogger(__name__)

# Consecutive identical words that mean the model has degenerated into a loop.
_REPEAT_WORDS = 25

# A provider that fails before sending a token is retried once; a provider that
# fails after tokens are on screen is not, because two partial answers would
# interleave.
_ANSWER_ATTEMPTS = 2
_ANSWER_RETRY_DELAY_SECONDS = 0.5


def _is_degenerate(pieces: list[str]) -> bool:
    """True when the answer tail is one word repeated, a small-model failure mode.

    gpt-oss-20b has been observed emitting a single token forever until the
    provider killed the stream, so this stops it first and keeps the partial
    answer, the citations and the persistence that follow.
    """
    tail = "".join(pieces[-40:])
    words = tail.split()
    if len(words) < _REPEAT_WORDS:
        return False
    recent = [word.strip(".,;:!?()[]\"'").lower() for word in words[-_REPEAT_WORDS:]]
    return len(set(recent)) == 1 and len(recent[0]) > 2

# ── Protected invariant ────────────────────────────────────────
# DO NOT modify this prompt without explicit instruction and
# verification against the out-of-scope question eval suite.
# This is a protected invariant per docs/architecture.md.

GROUNDING_SYSTEM_PROMPT = """You are a precise Q&A assistant grounded in a textbook. Your task is to answer the student's question using ONLY the provided context drawn from specific sections of the book.

## Rules

1. **Answer only from the provided context.** If the answer is not contained in the context, respond: "This is not covered in this section." Do not use your general knowledge.
2. **Cite sources.** For every factual claim, cite the source section and page range in the format: [Section: "Heading", pp. X–Y].
3. **Be precise.** If the question asks for a definition, give the definition as stated in the text. If it asks for an explanation, explain using the text's own examples.
4. **Be concise.** Answer in 2–4 paragraphs. Use plain language suitable for a university student.
5. **Quoting.** When quoting the text directly, wrap the quote in quote marks and cite the section.
6. **"Explain simpler" and "go deeper".** If the student asks for a simpler explanation, rephrase the same content in more accessible language using only the provided context. If they ask to go deeper, provide more detail from the context if available — but never go beyond it.
7. **Resolve references using conversation history.** If the question uses pronouns or shorthand ("this", "that", "the one above", "compare to before"), use the conversation history to identify what it refers to before answering. If a reference is genuinely ambiguous, briefly state your interpretation.

## Output format

Respond with the answer as plain prose — no JSON, no code fences. Where you rely on a specific passage, include an inline citation in the form [Section: "Heading", pp. X–Y]. Keep the answer self-contained and end after the final paragraph."""


# ── Context builder ────────────────────────────────────────────


CONTEXT_INSTRUCTIONS = """Sources and context.
- Passages marked role=match are the sources: answer only from them.
- Passages marked role=context show where those sources sit in the book. They are not sources.
- Also tag every passage you used with its number, like [1] or [1][3].
- The outline at the end lists nearby headings only; use it to say where a topic is covered."""


def _page_label(page_start: int, page_end: int) -> str:
    """'p. 79' for a single page, 'pp. 82-84' for a range."""
    if page_start == page_end:
        return f"p. {page_start}"
    return f"pp. {page_start}-{page_end}"


def _outline(passages: list[tuple[Any, float]]) -> str:
    """Headings around the matched sections, with the matches marked."""
    seen: set[tuple] = set()
    groups: list[str] = []
    for passage, _score in passages:
        if getattr(passage, "role", "match") != "match":
            continue
        siblings = getattr(passage, "siblings", ()) or ()
        if not siblings:
            continue
        key = tuple(siblings)
        if key in seen:
            continue
        seen.add(key)
        rendered = " | ".join(
            f"{heading} (matched)" if is_matched else heading
            for heading, is_matched in siblings
        )
        groups.append(f"- {rendered}")
    if not groups:
        return ""
    return "Outline near the matches (headings only):\n" + "\n".join(groups)


def build_context(
    passages: list[tuple[Any, float]],
) -> str:
    """Format retrieved passages with role, position and page range.

    Unit U9 changes only this function; ``GROUNDING_SYSTEM_PROMPT`` above is
    untouched. The instruction lives here, inside the user message, which is why
    the protected system prompt did not have to change.

    Args:
        passages: ``(passage, score)`` tuples, best first. A passage needs
            ``section`` and ``content``; ``role``, ``breadcrumb``, ``note`` and
            ``siblings`` are used when present, so a bare ``Chunk`` still works
            and renders as a match.

    Returns:
        Formatted context string for the user message.
    """
    if not passages:
        return CONTEXT_INSTRUCTIONS

    parts: list[str] = [CONTEXT_INSTRUCTIONS, "", "Passages:", ""]

    for rank, (passage, _score) in enumerate(passages, start=1):
        section = passage.section
        role = getattr(passage, "role", "match")
        path = getattr(passage, "breadcrumb", "") or section.heading
        header = (
            f"[{rank}] role={role} | {path} | "
            f"{_page_label(section.page_start, section.page_end)}"
        )
        note = getattr(passage, "note", "")
        if note:
            header += f" | {note}"
        parts.append(header)
        parts.append(passage.content)
        parts.append("")

    outline = _outline(passages)
    if outline:
        parts.append(outline)
        parts.append("")

    return "\n".join(parts)


# ── Pipeline function ──────────────────────────────────────────


async def answer_question_stream(
    question: str,
    context: str,
    *,
    summary: str | None = None,
    history: list[dict[str, str]] | None = None,
    model: str | None = None,
) -> AsyncGenerator[bytes, None]:
    """Stream a grounded Q&A answer as NDJSON events.

    Args:
        question: The student's question.
        context: Grounding context built by :func:`build_context`.
        model: LiteLLM model override. Defaults to ``QA_MODEL``.

    Yields:
        NDJSON-encoded ``{"type": "token", "text": "..."}`` lines. Citations
        and the ``done`` marker are emitted by the caller (router) from the
        retrieved chunks, not here.
    """
    model = model or QA_MODEL

    # Conversation history (rolling summary + recent messages) so the model can
    # resolve pronouns and cross-references across turns.
    history_block = ""
    if summary or history:
        lines = ["# Conversation so far"]
        if summary:
            lines.append(f"[Earlier] {summary}")
        for m in history or []:
            role = "User" if m.get("role") == "user" else "Assistant"
            content = m.get("content", "")
            if content.strip():
                lines.append(f"{role}: {content}")
        history_block = "\n".join(lines) + "\n\n"

    user_content = (
        f"{history_block}"
        f"# Student Question\n\n{question}\n\n"
        f"# Textbook Context\n\n{context}"
    )

    # A provider can fail before sending a single token (an error chunk, a
    # dropped connection, a rejected prompt). That is safe to retry: nothing has
    # been streamed yet, so a second attempt cannot duplicate output. Once any
    # token is out, a retry would interleave two partial answers, so the failure
    # is reported instead and the caller keeps what it has.
    for attempt in range(1, _ANSWER_ATTEMPTS + 1):
        emitted: list[str] = []
        try:
            response = await void_acompletion(
                model=model,
                messages=[
                    {"role": "system", "content": GROUNDING_SYSTEM_PROMPT},
                    {"role": "user", "content": user_content},
                ],
                temperature=0.2,
                stream=True,
                max_tokens=settings.qa_answer_max_tokens,
            )

            async for part in response:
                delta = part.choices[0].delta.content
                if not delta:
                    continue
                emitted.append(delta)
                yield json.dumps({"type": "token", "text": delta}).encode() + b"\n"

                if _is_degenerate(emitted):
                    logger.warning(
                        "Answer degenerated into repetition after %d chars; stopping",
                        sum(len(piece) for piece in emitted),
                    )
                    yield json.dumps({
                        "type": "error",
                        "text": (
                            "The answer started repeating itself and was stopped. "
                            "Ask again, or rephrase the question."
                        ),
                    }).encode() + b"\n"
                    return

            return

        except Exception as exc:  # noqa: BLE001 - provider failures
            chars = sum(len(piece) for piece in emitted)

            if chars == 0 and attempt < _ANSWER_ATTEMPTS:
                logger.warning(
                    "Answer stream failed before any token (attempt %d/%d): %s",
                    attempt,
                    _ANSWER_ATTEMPTS,
                    exc,
                )
                await asyncio.sleep(_ANSWER_RETRY_DELAY_SECONDS)
                continue

            # Either tokens are already on screen, or the retry also failed.
            # Either way the caller still emits citations, persists and sends
            # `done`, so the turn is not lost.
            logger.warning("Answer stream failed after %d chars: %s", chars, exc)
            text = (
                "The answer was cut off by the model provider. Try asking again."
                if chars
                else "The model provider did not respond. Try asking again."
            )
            yield json.dumps({"type": "error", "text": text}).encode() + b"\n"
            return


# ── Conversation summarisation ────────────────────────────────

SUMMARIZE_SYSTEM_PROMPT = """You are a conversation summarizer. Given a chat transcript between a student and an AI tutor studying a textbook, produce a concise running summary (2–5 sentences) that preserves the topics discussed, the questions asked, and the key answers, so future turns can be grounded in it without re-reading the full transcript. Do not invent content that is not in the transcript."""


async def summarize_conversation(messages: list[dict[str, str]]) -> str:
    """Summarize a chat transcript into a short running summary via VoidAI."""
    transcript = "\n".join(
        f"{m.get('role', 'unknown')}: {m.get('content', '')}" for m in messages
    )
    response = await void_acompletion(
        messages=[
            {"role": "system", "content": SUMMARIZE_SYSTEM_PROMPT},
            {"role": "user", "content": f"# Conversation transcript\n\n{transcript}"},
        ],
        temperature=0.2,
    )
    return response.choices[0].message.content
