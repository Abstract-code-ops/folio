"""LLM note generation (Pass 2).

Generates structured study notes for a single section using a grounded
LLM call (Cerebras via LiteLLM). The output follows a fixed schema:

  - concept_name
  - one-sentence definition
  - plain-language explanation
  - one example from the text
  - one self-check question

The LLM is grounded exclusively in the section heading, raw text, and
stored metadata — it does not draw on general knowledge.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from app.core.config import settings
from app.core.litellm import NOTE_GEN_MODEL, void_acompletion

# ── Output schemas ─────────────────────────────────────────────


class GeneratedConcept(BaseModel):
    """One concept extracted from a section."""

    name: str
    definition: str
    explanation: str
    example: str
    self_check: str


class GeneratedSectionNotes(BaseModel):
    """Notes generated for a single section."""

    section_id: str
    section_heading: str
    page_start: int
    page_end: int
    concepts: list[GeneratedConcept]


# ── Prompt template ───────────────────────────────────────────

SYSTEM_PROMPT = """You are a study-note generator grounded in a single textbook section. Your task is to extract key concepts from the provided section text and present them as structured study notes.

For each concept you identify, output:
1. **name** — the concept name (e.g. "Photosynthesis")
2. **definition** — a one-sentence academic definition
3. **explanation** — a plain-language explanation (As many sentences as you need to explain well)
4. **example** — one concrete example drawn from the provided text
5. **self_check** — a single question the student can use to test their understanding

Rules:
- Only extract concepts that are actually discussed in the provided text. Do not add external knowledge.
- If the section metadata lists concepts, use those as a starting point.
- Return your answer as a JSON object with a "concepts" array.
- Each concept object must have exactly the five fields above.
- Output 2–5 concepts per section.
- Do not include any text outside the JSON object."""


# ── Pipeline function ──────────────────────────────────────────


def _build_user_prompt(
    heading: str,
    raw_text: str,
    metadata: dict[str, Any] | None,
) -> str:
    """Build the user message with section content and metadata."""
    parts = [f"# Section: {heading}\n"]
    parts.append(f"## Full Text\n{raw_text}\n")

    if metadata:
        parts.append("## Section Metadata\n")
        if metadata.get("summary"):
            parts.append(f"Summary: {metadata['summary']}\n")
        if metadata.get("concepts"):
            parts.append(f"Key concepts: {', '.join(metadata['concepts'])}\n")
        if metadata.get("learning_objectives"):
            parts.append(
                f"Learning objectives: {', '.join(metadata['learning_objectives'])}\n"
            )
        if metadata.get("definitions"):
            parts.append(f"Definitions: {', '.join(metadata['definitions'])}\n")
        if metadata.get("equations"):
            parts.append(f"Equations: {', '.join(metadata['equations'])}\n")
        if metadata.get("examples"):
            parts.append(f"Examples: {', '.join(metadata['examples'])}\n")

    parts.append(
        "\nGenerate structured study notes for the concepts in this section. "
        "Return ONLY a JSON object with a 'concepts' array."
    )
    return "\n".join(parts)


async def generate_section_notes(
    section_id: str,
    heading: str,
    raw_text: str,
    page_start: int,
    page_end: int,
    metadata: dict[str, Any] | None = None,
    *,
    model: str | None = None,
) -> GeneratedSectionNotes:
    """Generate structured study notes for a single section.

    Args:
        section_id: UUID string of the section.
        heading: Section heading.
        raw_text: Full raw text of the section.
        page_start: Starting page number.
        page_end: Ending page number.
        metadata: Optional section metadata dict (concepts, summary, etc.).
        model: LiteLLM model override. Defaults to ``NOTE_GEN_MODEL``.

    Returns:
        ``GeneratedSectionNotes`` with extracted concepts.
    """
    model = model or NOTE_GEN_MODEL
    user_prompt = _build_user_prompt(heading, raw_text, metadata)

    response = await void_acompletion(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        response_format={"type": "json_object"},
        temperature=0.3,
    )

    content = response.choices[0].message.content

    # Parse the response into our schema
    import json

    parsed = json.loads(content)

    return GeneratedSectionNotes(
        section_id=section_id,
        section_heading=heading,
        page_start=page_start,
        page_end=page_end,
        concepts=[GeneratedConcept(**c) for c in parsed["concepts"]],
    )
