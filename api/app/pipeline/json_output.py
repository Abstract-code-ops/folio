"""Parsing model output that is supposed to be a JSON object.

Every stage that asks a model for JSON mode hits the same three failure modes:
an empty reply, truncated or malformed JSON, and a JSON value that is not an
object at all. Collecting them here means each stage reports them in its own
error type instead of leaking a bare ``JSONDecodeError`` from deep inside the
pipeline, and the fence-trimming logic exists once.
"""

from __future__ import annotations

import json
from typing import Any


class JsonOutputError(ValueError):
    """The model's reply was not a usable JSON object."""


def parse_json_object(content: str | None, *, context: str) -> dict[str, Any]:
    """Parse a JSON object, tolerating a Markdown code fence.

    ``context`` names the caller in the error message, e.g.
    ``"note generation for section abc"``.
    """
    text = (content or "").strip()
    if text.startswith("```"):
        lines = text.splitlines()[1:]
        while lines and not lines[-1].strip():
            lines.pop()
        if lines and lines[-1].strip().startswith("```"):
            lines.pop()
        text = "\n".join(lines).strip()

    if not text:
        raise JsonOutputError(f"{context} returned an empty response")

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise JsonOutputError(
            f"{context} returned malformed or truncated JSON: {exc.msg} "
            f"at position {exc.pos}"
        ) from exc

    if not isinstance(parsed, dict):
        raise JsonOutputError(
            f"{context} returned a {type(parsed).__name__}, expected a JSON object"
        )
    return parsed
