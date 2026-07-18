"""Section metadata extraction (Pass 1 — LLM).

Extracts structured metadata from section heading + raw text using
Gemini SDK directly (not through LiteLLM).

Uses tenacity for retry on rate limits. Gemini is the only provider
used here — note gen and Q&A still use Cerebras via LiteLLM elsewhere.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from google import genai
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from app.core.config import settings

logger = logging.getLogger(__name__)

# ── Prompts ────────────────────────────────────────────────────

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
- Return ONLY the JSON object, no other text."""

BATCH_SYSTEM_PROMPT = """You are a textbook metadata extractor. You will receive MULTIPLE sections at once. For EACH section, extract the following fields and return them as a JSON object with a "sections" array:

{
  "sections": [
    {
      "section_index": 0,
      "learning_objectives": ["..."],
      "summary": "...",
      "concepts": ["..."],
      "definitions": ["..."],
      "equations": ["..."],
      "examples": ["..."],
      "exercise_count": 0
    }
  ]
}

Rules:
- Only extract what is actually present in the text.
- If a field has no content, return an empty list or 0.
- Return ONLY the JSON object, no other text."""


# ── Normalisation ──────────────────────────────────────────────


def _normalise_metadata(parsed: dict) -> dict[str, Any]:
    return {
        "learning_objectives": parsed.get("learning_objectives", []),
        "summary": parsed.get("summary", ""),
        "concepts": parsed.get("concepts", []),
        "definitions": parsed.get("definitions", []),
        "equations": parsed.get("equations", []),
        "examples": parsed.get("examples", []),
        "exercise_count": parsed.get("exercise_count", 0),
    }


# ── Gemini SDK call ────────────────────────────────────────────


def _is_rate_limit(e: Exception) -> bool:
    """Check if an exception is a Gemini rate-limit error."""
    msg = str(e).lower()
    return "429" in msg or "rate_limit" in msg or "quota" in msg or "resource_exhausted" in msg


# Initialise Gemini client once at module level
_gemini_client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))


async def _call_gemini(system_prompt: str, user_prompt: str) -> dict[str, Any]:
    """Call Gemini directly via google-genai SDK with retry.

    Runs the synchronous SDK call in a thread to avoid blocking the event loop.
    Returns the parsed JSON dict.
    """
    model = settings.gemini_metadata_model
    full_prompt = f"{system_prompt}\n\n{user_prompt}"

    @retry(
        stop=stop_after_attempt(settings.gemini_max_retries),
        wait=wait_exponential(multiplier=2, min=10, max=120),
        retry=retry_if_exception(_is_rate_limit),
        before_sleep=lambda rs: logger.info(
            "Gemini rate limited — retrying in %ds (attempt %d/%d)",
            rs.next_action.sleep if hasattr(rs.next_action, "sleep") else 10,
            rs.attempt_number,
            settings.gemini_max_retries,
        ),
        reraise=True,
    )
    def _call() -> str:
        response = _gemini_client.models.generate_content(
            model=model,
            contents=full_prompt,
            config={
                "response_mime_type": "application/json",
                "temperature": 0.1,
                "max_output_tokens": 4096,
            },
        )
        return response.text

    content = await asyncio.to_thread(_call)
    return json.loads(content)


# ── Public API ─────────────────────────────────────────────────


async def extract_metadata(
    heading: str,
    raw_text: str,
    *,
    model: str | None = None,
) -> dict[str, Any]:
    """Extract metadata for a single section."""
    _ = model
    words = raw_text.split()
    truncated = " ".join(words[:6000]) if len(words) > 6000 else raw_text
    user_prompt = f"# Section Heading\n{heading}\n\n# Section Text\n{truncated}"
    parsed = await _call_gemini(SYSTEM_PROMPT, user_prompt)
    return _normalise_metadata(parsed)


async def extract_metadata_batch(
    sections: list[tuple[str, str]],
    *,
    model: str | None = None,
    batch_size: int = 10,
) -> list[dict[str, Any]]:
    """Extract metadata for MULTIPLE sections in batches.

    Each batch is one Gemini call. Returns metadata in same order as input.
    """
    _ = model
    results: list[dict[str, Any]] = [None] * len(sections)  # type: ignore

    # Group into batches
    batches: list[list[tuple[int, str, str]]] = []
    for i, (heading, raw_text) in enumerate(sections):
        if batches and len(batches[-1]) < batch_size:
            batches[-1].append((i, heading, raw_text))
        else:
            batches.append([(i, heading, raw_text)])

    logger.info("Split %d sections into %d batches (batch_size=%d)", len(sections), len(batches), batch_size)

    for batch_idx, batch in enumerate(batches):
        logger.info("Batch %d/%d (%d sections)", batch_idx + 1, len(batches), len(batch))

        # Build prompt
        parts = []
        for idx_in_batch, (_, heading, raw_text) in enumerate(batch):
            words = raw_text.split()
            truncated = " ".join(words[:2000]) if len(words) > 2000 else raw_text
            parts.append(f"--- Section {idx_in_batch} ---")
            parts.append(f"Heading: {heading}")
            parts.append(f"Full Text:\n{truncated}\n")
        user_prompt = "\n".join(parts)

        try:
            parsed = await _call_gemini(BATCH_SYSTEM_PROMPT, user_prompt)
            for entry in parsed.get("sections", []):
                idx_in_batch = entry.get("section_index")
                if idx_in_batch is not None and idx_in_batch < len(batch):
                    original_idx = batch[idx_in_batch][0]
                    results[original_idx] = _normalise_metadata(entry)
        except Exception as e:
            logger.warning("Batch %d failed after retries: %s", batch_idx + 1, e)
            for idx_in_batch, (original_idx, _, _) in enumerate(batch):
                if results[original_idx] is None:
                    results[original_idx] = _normalise_metadata({})

        # Delay between batches
        if batch_idx < len(batches) - 1:
            logger.debug("Waiting 70s before next batch...")
            await asyncio.sleep(70)

        filled = sum(1 for r in results if r is not None)
        logger.info("Progress: %d/%d after batch %d", filled, len(sections), batch_idx + 1)

    return results


# Need asyncio for sleep
import asyncio  # noqa: E402