"""Retrieval and grounded Q&A response generation.

The Q&A is scoped to a **book** — the pipeline searches all sections
of the book for relevant chunks, retrieves the top-k most similar,
and streams a grounded answer with per-section source citations.

Protected invariant: ``GROUNDING_SYSTEM_PROMPT`` is the Q&A grounding
system prompt. It is never overridden or appended to by user input.
Changes to it require an explicit code change and must be tested
against the out-of-scope question eval suite before deployment
(see architecture.md).
"""

from __future__ import annotations

import json
from typing import Any, AsyncGenerator

from litellm import acompletion

from app.core.litellm import QA_MODEL

# ── Protected invariant ────────────────────────────────────────
# DO NOT modify this prompt without explicit instruction and
# verification against the out-of-scope question eval suite.
# This is a protected invariant per architecture.md.

GROUNDING_SYSTEM_PROMPT = """You are a precise Q&A assistant grounded in a textbook. Your task is to answer the student's question using ONLY the provided context drawn from specific sections of the book.

## Rules

1. **Answer only from the provided context.** If the answer is not contained in the context, respond: "This is not covered in this section." Do not use your general knowledge.
2. **Cite sources.** For every factual claim, cite the source section and page range in the format: [Section: "Heading", pp. X–Y].
3. **Be precise.** If the question asks for a definition, give the definition as stated in the text. If it asks for an explanation, explain using the text's own examples.
4. **Be concise.** Answer in 2–4 paragraphs. Use plain language suitable for a university student.
5. **Quoting.** When quoting the text directly, wrap the quote in quote marks and cite the section.
6. **"Explain simpler" and "go deeper".** If the student asks for a simpler explanation, rephrase the same content in more accessible language using only the provided context. If they ask to go deeper, provide more detail from the context if available — but never go beyond it.

## Output format

Return your answer as a JSON object with two fields:
- "answer": the full answer text (with inline citations in [Section, pp. X–Y] format)
- "citations": an array of source citation objects, each with:
  - "section_heading": string
  - "page_start": int (if available, else null)
  - "page_end": int (if available, else null)
  - "excerpt": string (the specific sentence or two you cited)"""


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
        parts.append(chunk.content)
        parts.append("")

    return "\n".join(parts)


# ── Pipeline function ──────────────────────────────────────────


async def answer_question_stream(
    question: str,
    context: str,
    *,
    model: str | None = None,
) -> AsyncGenerator[bytes, None]:
    """Stream a grounded Q&A answer as NDJSON events.

    Args:
        question: The student's question.
        context: Grounding context built by :func:`build_context`.
        model: LiteLLM model override. Defaults to ``QA_MODEL``.

    Yields:
        NDJSON-encoded bytes lines:
        - ``{"type": "token", "text": "..."}`` — answer text tokens
        - ``{"type": "citation", ...}`` — source citation objects
        - ``{"type": "done"}`` — end of stream
    """
    model = model or QA_MODEL

    response = await acompletion(
        model=model,
        messages=[
            {"role": "system", "content": GROUNDING_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"# Student Question\n\n{question}\n\n"
                f"# Textbook Context\n\n{context}",
            },
        ],
        response_format={"type": "json_object"},
        temperature=0.2,
        stream=False,
    )

    content = response.choices[0].message.content
    parsed = json.loads(content)

    answer = parsed.get("answer", "")
    citations = parsed.get("citations", [])

    # Yield the answer in sentence-sized pieces for natural streaming
    import re
    sentences = re.split(r"(?<=[.!?])\s+", answer)
    for sentence in sentences:
        if sentence.strip():
            yield json.dumps({
                "type": "token",
                "text": sentence + " ",
            }).encode() + b"\n"

    # Yield citations (section_heading now comes from the LLM)
    for citation in citations:
        yield json.dumps({
            "type": "citation",
            "section_heading": citation.get("section_heading"),
            "page_start": citation.get("page_start"),
            "page_end": citation.get("page_end"),
            "excerpt": citation.get("excerpt"),
        }).encode() + b"\n"

    yield json.dumps({"type": "done"}).encode() + b"\n"
