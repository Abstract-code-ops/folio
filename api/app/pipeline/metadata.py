"""Section metadata extraction (Pass 1 — LLM).

Extracts structured metadata from a single section's heading + raw text
using LiteLLM (Gemini). The extracted metadata is stored in the
``section.section_metadata`` JSONB column and later used at note
generation time.

Extracted fields (from the Section model):
  - learning_objectives: list[str]
  - summary: str
  - concepts: list[str]
  - definitions: list[str]
  - equations: list[str]
  - examples: list[str]
  - exercise_count: int
"""

from __future__ import annotations

import json
import logging
from typing import Any

from litellm import acompletion

from app.core.litellm import METADATA_MODEL

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a textbook metadata extractor. Given a section heading and its full text, extract the following fields and return them as a JSON object:

{
  "learning_objectives": ["..."],
  "summary": "A 2-3 sentence summary of the section",
  "concepts": ["key concept 1", "key concept 2", ...],
  "definitions": ["term: definition", ...],
  "equations": ["equation text", ...],
  "examples": ["example text", ...],
  "exercise_count": 0
}

Rules:
- Only extract what is actually present in the text. Do not invent content.
- If a field has no content in the text, return an empty list or 0.
- Concepts should be the key technical terms introduced in this section.
- Definitions should pair each defined term with its definition.
- Equations should be extracted verbatim where possible.
- Examples should be concrete instances or applications from the text.
- The summary should capture the main pedagogical point of the section.
- Exercise count is the number of practice problems or exercises at the end of the section.
- Return ONLY the JSON object, no other text."""


async def extract_metadata(
    heading: str,
    raw_text: str,
    *,
    model: str | None = None,
) -> dict[str, Any]:
    """Extract structured metadata from a section heading + raw text.

    Args:
        heading: Section heading (e.g. "Photosynthesis: Light Reactions").
        raw_text: Full raw text of the section.
        model: LiteLLM model override. Defaults to ``METADATA_MODEL``
            (Gemini from config).

    Returns:
        Dict with keys: learning_objectives, summary, concepts,
        definitions, equations, examples, exercise_count.
    """
    model = model or METADATA_MODEL

    # Truncate raw_text to avoid exceeding context windows
    # (~8k tokens should be enough for any section)
    words = raw_text.split()
    if len(words) > 6000:
        truncated = " ".join(words[:6000])
        logger.info("Truncated section '%s' from %d to 6000 words", heading, len(words))
    else:
        truncated = raw_text

    user_prompt = (
        f"# Section Heading\n{heading}\n\n"
        f"# Section Text\n{truncated}"
    )

    response = await acompletion(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        response_format={"type": "json_object"},
        temperature=0.1,
    )

    content = response.choices[0].message.content
    parsed = json.loads(content)

    # Normalise the response to ensure all expected keys exist
    return {
        "learning_objectives": parsed.get("learning_objectives", []),
        "summary": parsed.get("summary", ""),
        "concepts": parsed.get("concepts", []),
        "definitions": parsed.get("definitions", []),
        "equations": parsed.get("equations", []),
        "examples": parsed.get("examples", []),
        "exercise_count": parsed.get("exercise_count", 0),
    }