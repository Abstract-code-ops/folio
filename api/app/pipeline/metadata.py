"""Section metadata extraction (Pass 1 — LLM).

Extracts structured metadata from section heading + raw text using
Gemini SDK directly (not through LiteLLM).

Uses tenacity for retry on rate limits. Gemini is the only provider
used here — note gen and Q&A still use Cerebras via LiteLLM elsewhere.
"""

from __future__ import annotations

import asyncio
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


# ── Section status values ──────────────────────────────────────
#
# Recorded inside the existing ``section_metadata`` JSON under "status", so
# no column is needed. The distinction that matters:
#   ok      - a non-empty summary came back.
#   partial - the model answered, but the summary is empty. Front matter
#             (cover, copyright, colophon, contents) genuinely has nothing to
#             summarise. Re-asking would waste calls, so this is terminal.
#   failed  - no usable answer after every attempt.

METADATA_STATUS_OK = "ok"
METADATA_STATUS_PARTIAL = "partial"
METADATA_STATUS_FAILED = "failed"


# ── Normalisation ──────────────────────────────────────────────


def _normalise_metadata(
    parsed: dict,
    *,
    status: str | None = None,
) -> dict[str, Any]:
    """Normalise one section's extracted fields and stamp its outcome status.

    When ``status`` is omitted it is derived from the summary, so the
    single-section path obeys the same contract as the batch path.
    """
    summary = parsed.get("summary") or ""
    if status is None:
        status = (
            METADATA_STATUS_OK if summary.strip() else METADATA_STATUS_PARTIAL
        )
    return {
        "learning_objectives": parsed.get("learning_objectives", []),
        "summary": summary,
        "concepts": parsed.get("concepts", []),
        "definitions": parsed.get("definitions", []),
        "equations": parsed.get("equations", []),
        "examples": parsed.get("examples", []),
        "exercise_count": parsed.get("exercise_count", 0),
        "status": status,
    }


# ── Gemini SDK call ────────────────────────────────────────────


# Markers for failures worth retrying in place. A 503 ("this model is
# currently experiencing high demand") is transient, but the predicate used to
# look for 429s only, so an overloaded model skipped the retry and fell
# straight through to the repair pass.
_TRANSIENT_MARKERS = (
    "429",
    "rate_limit",
    "quota",
    "resource_exhausted",
    "500",
    "502",
    "503",
    "504",
    "unavailable",
    "overloaded",
    "deadline",
)


def _is_transient_error(e: Exception) -> bool:
    """True for rate-limit and transient server errors worth retrying."""
    message = str(e).lower()
    return any(marker in message for marker in _TRANSIENT_MARKERS)


# Gemini client, created on first use. Lazy so importing this module (tests,
# type checks, tooling) does not require GEMINI_API_KEY to be present.
_gemini_client: genai.Client | None = None


def _get_gemini_client() -> genai.Client:
    """Return the shared Gemini client, creating it on first call."""
    global _gemini_client
    if _gemini_client is None:
        _gemini_client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
    return _gemini_client


def _strip_code_fence(text: str) -> str:
    """Remove a Markdown code fence around a JSON payload.

    The prompt asks for bare JSON, but models occasionally wrap it in
    ```json fences. Without this the batch raises, and before U2 that cost
    every section in the batch.
    """
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()[1:]
    while lines and not lines[-1].strip():
        lines.pop()
    if lines and lines[-1].strip().startswith("```"):
        lines.pop()
    return "\n".join(lines).strip()


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
        retry=retry_if_exception(_is_transient_error),
        before_sleep=lambda rs: logger.info(
            "Gemini transient error - retrying in %ds (attempt %d/%d)",
            rs.next_action.sleep if hasattr(rs.next_action, "sleep") else 10,
            rs.attempt_number,
            settings.gemini_max_retries,
        ),
        reraise=True,
    )
    def _call() -> str:
        response = _get_gemini_client().models.generate_content(
            model=model,
            contents=full_prompt,
            config={
                "response_mime_type": "application/json",
                "temperature": 0.1,
                "max_output_tokens": settings.gemini_metadata_max_output_tokens,
            },
        )
        return response.text

    content = await asyncio.to_thread(_call)
    parsed = json.loads(_strip_code_fence(content))
    if not isinstance(parsed, dict):
        raise ValueError(
            f"expected a JSON object, got {type(parsed).__name__}"
        )
    return parsed


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


def _batch_prompt(sections: list[tuple[str, str]], indices: list[int]) -> str:
    """Build the user prompt for one batch of section indices."""
    parts: list[str] = []
    for idx_in_batch, original_idx in enumerate(indices):
        heading, raw_text = sections[original_idx]
        words = raw_text.split()
        truncated = " ".join(words[:2000]) if len(words) > 2000 else raw_text
        parts.append(f"--- Section {idx_in_batch} ---")
        parts.append(f"Heading: {heading}")
        parts.append(f"Full Text:\n{truncated}\n")
    return "\n".join(parts)


async def _request_batch(
    sections: list[tuple[str, str]],
    indices: list[int],
    results: list[dict[str, Any] | None],
    *,
    label: str,
) -> list[int]:
    """Make one call for ``indices``, fill ``results``, return what is missing.

    A section is filled only when the response actually contains it. A raised
    call or an absent entry leaves it ``None``, which the caller re-requests.
    Nothing is ever filled with an empty placeholder here - that was the bug
    that lost a whole batch silently.
    """
    try:
        parsed = await _call_gemini(BATCH_SYSTEM_PROMPT, _batch_prompt(sections, indices))
    except Exception as exc:  # noqa: BLE001 - one bad batch must not kill the run
        logger.warning(
            "%s failed (%s); %d section(s) left for repair",
            label,
            exc,
            len(indices),
        )
        return list(indices)

    answered: set[int] = set()
    entries = parsed.get("sections")
    if not isinstance(entries, list):
        logger.warning("%s returned no 'sections' array; %d left for repair", label, len(indices))
        return list(indices)

    for entry in entries:
        if not isinstance(entry, dict):
            continue
        try:
            idx_in_batch = int(entry.get("section_index"))
        except (TypeError, ValueError):
            continue
        if not 0 <= idx_in_batch < len(indices):
            continue
        original_idx = indices[idx_in_batch]
        results[original_idx] = _normalise_metadata(entry)
        answered.add(original_idx)

    return [idx for idx in indices if idx not in answered]


async def extract_metadata_batch(
    sections: list[tuple[str, str]],
    *,
    model: str | None = None,
    batch_size: int | None = None,
) -> list[dict[str, Any]]:
    """Extract metadata for multiple sections, repairing dropped sections.

    Sections that come back unanswered are re-requested in smaller batches,
    up to ``settings.gemini_metadata_repair_attempts`` extra passes. Every
    returned dict carries ``status`` of ``ok``, ``partial`` or ``failed``, so
    an empty summary can never be mistaken for a section that was never
    processed.
    """
    _ = model
    size = batch_size or settings.gemini_metadata_batch_size
    if not sections:
        return []

    results: list[dict[str, Any] | None] = [None] * len(sections)
    logger.info(
        "Extracting metadata for %d sections (batch_size=%d, repair_attempts=%d)",
        len(sections),
        size,
        settings.gemini_metadata_repair_attempts,
    )

    pending = list(range(len(sections)))
    total_passes = settings.gemini_metadata_repair_attempts + 1

    for attempt in range(1, total_passes + 1):
        if not pending:
            break
        # Repair passes halve the batch: less output pressure per call.
        pass_size = size if attempt == 1 else max(1, size // 2)
        groups = [
            pending[i : i + pass_size] for i in range(0, len(pending), pass_size)
        ]
        if attempt > 1:
            logger.info(
                "Metadata repair pass %d: re-requesting %d section(s) in %d batch(es)",
                attempt - 1,
                len(pending),
                len(groups),
            )

        still_missing: list[int] = []
        for n, group in enumerate(groups, start=1):
            still_missing.extend(
                await _request_batch(
                    sections,
                    group,
                    results,
                    label=f"Metadata pass {attempt} batch {n}/{len(groups)}",
                )
            )
            if n < len(groups):
                await asyncio.sleep(settings.gemini_batch_delay_seconds)

        pending = still_missing

    # Anything still unanswered is explicitly failed - never silently empty.
    for idx, result in enumerate(results):
        if result is None:
            results[idx] = _normalise_metadata({}, status=METADATA_STATUS_FAILED)

    counts = {
        METADATA_STATUS_OK: 0,
        METADATA_STATUS_PARTIAL: 0,
        METADATA_STATUS_FAILED: 0,
    }
    failed_headings: list[str] = []
    for idx, result in enumerate(results):
        if result is None:  # narrowed above; keeps the type checker honest
            continue
        status = result["status"]
        counts[status] = counts.get(status, 0) + 1
        heading = sections[idx][0][:60]
        if status == METADATA_STATUS_OK:
            logger.debug("Metadata ok: section %d '%s'", idx, heading)
            continue
        logger.info("Metadata %s: section %d '%s'", status, idx, heading)
        if status == METADATA_STATUS_FAILED:
            failed_headings.append(heading)

    logger.info(
        "Metadata complete: %d ok, %d partial, %d failed of %d",
        counts[METADATA_STATUS_OK],
        counts[METADATA_STATUS_PARTIAL],
        counts[METADATA_STATUS_FAILED],
        len(sections),
    )
    if failed_headings:
        logger.warning(
            "Metadata failed for %d section(s): %s",
            len(failed_headings),
            "; ".join(failed_headings[:20]),
        )

    return [r for r in results if r is not None]