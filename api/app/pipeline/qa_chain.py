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

import json
from typing import Any, AsyncGenerator

from app.core.litellm import QA_MODEL, void_acompletion

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


def build_context(
    chunks: list[tuple[Any, float]],
) -> str:
    """Format retrieved chunks with per-chunk section info as a grounding context string.

    Each chunk is expected to have its ``section`` relationship loaded
    (``joinedload(Chunk.section)``) so that section heading and page
    range can be included in the context.

    Args:
        chunks: List of ``(chunk, similarity_score)`` tuples, sorted
            by descending score.

    Returns:
        Formatted context string for the LLM prompt.
    """
    parts = ["The following passages are drawn from various sections of the book.\n"]

    for rank, (chunk, score) in enumerate(chunks, start=1):
        section = chunk.section
        sec_info = f"Section: \"{section.heading}\" (pp. {section.page_start}–{section.page_end})"
        parts.append(f"[Chunk {rank} — {sec_info}]")
        summary = (section.section_metadata or {}).get("summary")
        if summary:
            parts.append(f"Section summary: {summary}")
        parts.append(chunk.content)
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

    response = await void_acompletion(
        model=model,
        messages=[
            {"role": "system", "content": GROUNDING_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        temperature=0.2,
        stream=True,
    )

    async for part in response:
        delta = part.choices[0].delta.content
        if delta:
            yield json.dumps({"type": "token", "text": delta}).encode() + b"\n"


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
