"""Figure / diagram ingestion helpers.

Detects figure regions on a page (raster images **and** vector diagrams),
crops a PNG for captioning, and captions it with a vision model under a rate
limiter. Nothing here touches the database or storage — captions are stored as
``kind="figure"`` chunks (content = caption, bbox = region) by the ingest
worker.

Design notes:

* **All diagram types.** Raster image rects (``get_image_info``) and vector
  drawing rects (``get_drawings``) are clustered into regions; small clusters
  (rules, logos, icons) are dropped, and any region overlapping a table is
  excluded so table gridlines are not re-captioned as figures.
* **Rate-limited.** ``CaptionPacer`` enforces a requests/minute and
  requests/day budget (Gemma free tier: 30 RPM / 14,400 RPD). A provider 429
  is retried after its ``retryDelay``; when a retry still fails, the phase
  raises ``QuotaExhausted`` so ingest can soft-stop and resume later.
* Nothing here is imported by the parser or chunker, so this stays a leaf.
"""

from __future__ import annotations

import asyncio
import re
import time
from collections import deque
from typing import Awaitable, Callable, Iterable, Optional

# A figure region: (1-based page number, (x0, y0, x1, y1)).
FigureRegion = tuple[int, tuple[float, float, float, float]]

# generator(prompt, png_bytes) -> caption text
Generator = Callable[[str, bytes], Awaitable[str]]


class QuotaExhausted(Exception):
    """Raised when the daily caption budget (or repeated 429s) is spent."""


# ── Geometry helpers ──────────────────────────────────────────


def _rect_tuple(rect: object) -> tuple[float, float, float, float]:
    if hasattr(rect, "x0"):
        return (float(rect.x0), float(rect.y0), float(rect.x1), float(rect.y1))  # type: ignore[attr-defined]
    r = rect  # sequence of 4
    return (float(r[0]), float(r[1]), float(r[2]), float(r[3]))  # type: ignore[index]


def _area(rect: tuple[float, float, float, float]) -> float:
    return max(0.0, rect[2] - rect[0]) * max(0.0, rect[3] - rect[1])


def _near(
    a: tuple[float, float, float, float],
    b: tuple[float, float, float, float],
    gap: float,
) -> bool:
    """True when the rectangles touch or are within ``gap`` points."""
    return not (
        a[2] + gap < b[0]
        or b[2] + gap < a[0]
        or a[3] + gap < b[1]
        or b[3] + gap < a[1]
    )


def _union(
    a: tuple[float, float, float, float],
    b: tuple[float, float, float, float],
) -> tuple[float, float, float, float]:
    return (min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3]))


def _overlaps(
    a: tuple[float, float, float, float],
    b: tuple[float, float, float, float],
) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def _merge_rects(
    rects: Iterable[tuple[float, float, float, float]],
    gap: float,
) -> list[tuple[float, float, float, float]]:
    """Merge rectangles that touch/overlap within ``gap`` into regions."""
    items = [tuple(r) for r in rects]
    changed = True
    while changed:
        changed = False
        result: list[tuple[float, float, float, float]] = []
        for rect in items:
            for i, other in enumerate(result):
                if _near(rect, other, gap):
                    result[i] = _union(rect, other)
                    changed = True
                    break
            else:
                result.append(rect)
        items = result
    return items


# ── Region detection ──────────────────────────────────────────


def iter_figure_regions(
    doc,
    *,
    exclude: Iterable[tuple[int, tuple[float, float, float, float]]] = (),
    min_area_ratio: float = 0.03,
    min_side: float = 60.0,
    gap: float = 12.0,
) -> list[FigureRegion]:
    """Return figure regions across the document.

    ``exclude`` is ``(page, rect)`` pairs to skip — used to drop regions that
    overlap a table. A region must cover at least ``min_area_ratio`` of the
    page and be at least ``min_side`` points on both axes.
    """
    exclude_by_page: dict[int, list[tuple[float, float, float, float]]] = {}
    for page_no, rect in exclude:
        exclude_by_page.setdefault(page_no, []).append(tuple(rect))

    regions: list[FigureRegion] = []
    for index in range(doc.page_count):
        page_no = index + 1
        try:
            page = doc.load_page(index)
        except Exception:  # noqa: BLE001 - a bad page must not abort the scan
            continue
        page_area = float(page.rect.width) * float(page.rect.height)
        if page_area <= 0:
            continue

        rects: list[tuple[float, float, float, float]] = []
        try:
            for info in page.get_image_info():
                bbox = info.get("bbox") if isinstance(info, dict) else None
                if bbox is not None:
                    rects.append(_rect_tuple(bbox))
        except Exception:  # noqa: BLE001
            pass
        try:
            for drawing in page.get_drawings():
                rect = drawing.get("rect") if isinstance(drawing, dict) else None
                if rect is not None:
                    rects.append(_rect_tuple(rect))
        except Exception:  # noqa: BLE001
            pass

        rects = [r for r in rects if _area(r) > 0]
        for region in _merge_rects(rects, gap):
            if _area(region) < min_area_ratio * page_area:
                continue
            if (region[2] - region[0]) < min_side or (region[3] - region[1]) < min_side:
                continue
            if any(_overlaps(region, ex) for ex in exclude_by_page.get(page_no, [])):
                continue
            regions.append((page_no, region))
    return regions


def crop_png(page, bbox: tuple[float, float, float, float], dpi: int) -> bytes:
    """Render a page region to PNG bytes."""
    import fitz  # PyMuPDF

    clip = fitz.Rect(bbox[0], bbox[1], bbox[2], bbox[3])
    pix = page.get_pixmap(clip=clip, dpi=dpi)
    return pix.tobytes("png")


# ── Captioning ────────────────────────────────────────────────


class CaptionPacer:
    """Async gate for a requests/minute and requests/day budget.

    ``now`` and ``sleep`` are injectable so the pacing can be tested without
    real time. Raises :class:`QuotaExhausted` once the daily budget is spent.
    """

    def __init__(
        self,
        *,
        rpm: int = 30,
        rpd: int = 14400,
        now: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._rpm = max(1, rpm)
        self._rpd = max(1, rpd)
        self._now = now
        self._sleep = sleep
        self._window: deque[float] = deque()
        self._day_start = now()
        self._used_today = 0

    async def acquire(self) -> None:
        t = self._now()
        if t - self._day_start >= 86400:
            self._day_start = t
            self._used_today = 0
        if self._used_today >= self._rpd:
            raise QuotaExhausted("daily figure-caption quota reached")

        while self._window and t - self._window[0] >= 60:
            self._window.popleft()
        if len(self._window) >= self._rpm:
            wait = 60 - (t - self._window[0]) + 0.5
            if wait > 0:
                await self._sleep(wait)
            t = self._now()
            while self._window and t - self._window[0] >= 60:
                self._window.popleft()

        self._window.append(t)
        self._used_today += 1


_RETRY_DELAY_RE = re.compile(r"retryDelay['\"]?\s*[:=]\s*['\"]?(\d+)")


def _is_rate_limit(exc: Exception) -> bool:
    message = str(exc)
    return (
        "429" in message
        or "RESOURCE_EXHAUSTED" in message
        or "quota" in message.lower()
        or "rate limit" in message.lower()
    )


def _is_transient(exc: Exception) -> bool:
    """True for provider 5xx / timeout style errors worth retrying."""
    message = str(exc)
    return any(
        token in message
        for token in (
            "500",
            "502",
            "503",
            "504",
            "INTERNAL",
            "UNAVAILABLE",
            "Deadline",
            "timeout",
            "Timeout",
            "temporarily",
        )
    )


async def generate_with_backoff(
    generator: Generator,
    prompt: str,
    png: bytes,
    *,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    max_retries: int = 4,
) -> str:
    """Call ``generator``, retrying rate-limit and transient (5xx) errors.

    - Rate limit (429 / RESOURCE_EXHAUSTED): wait ``retryDelay`` and retry; a
      rate limit that survives the final attempt becomes ``QuotaExhausted``.
    - Transient server error (500 / 503 / INTERNAL / timeout): exponential
      backoff retry — Gemma returns these intermittently.
    - Anything else: re-raised immediately (a real, non-retryable error).
    """
    for attempt in range(max_retries):
        try:
            return await generator(prompt, png)
        except Exception as exc:  # noqa: BLE001
            last = attempt == max_retries - 1
            if _is_rate_limit(exc):
                if last:
                    raise QuotaExhausted(str(exc)) from exc
                match = _RETRY_DELAY_RE.search(str(exc))
                await sleep(min(int(match.group(1)) if match else 20, 60))
            elif _is_transient(exc):
                if last:
                    raise
                await sleep(min(2.0 ** attempt * 2.0, 30.0))
            else:
                raise
    raise QuotaExhausted("rate limited")  # unreachable, satisfies typing


def _build_caption_prompt(heading: str, nearby_text: str) -> str:
    context = " ".join((nearby_text or "").split())[:800]
    return (
        "You are captioning a figure from a computer-science textbook section "
        f"titled {heading!r}. In 1-2 sentences, describe only what the figure or "
        "diagram shows. Do not add outside knowledge. "
        f"Nearby text for context:\n{context}"
    )


def _clean_caption(text: str) -> str:
    """Take the model's final paragraph, collapse whitespace, cap the length."""
    if not text:
        return ""
    paragraphs = [p.strip() for p in text.strip().split("\n\n") if p.strip()]
    cleaned = paragraphs[-1] if paragraphs else text
    cleaned = " ".join(cleaned.split())
    return cleaned[:500]


async def caption_figure(
    png: bytes,
    heading: str,
    nearby_text: str,
    *,
    generator: Generator,
    pacer: CaptionPacer,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> str:
    """Pace, generate and clean one figure caption."""
    await pacer.acquire()
    prompt = _build_caption_prompt(heading, nearby_text)
    raw = await generate_with_backoff(generator, prompt, png, sleep=sleep)
    return _clean_caption(raw)


def gemini_generator(*, model: str, max_tokens: int) -> Generator:
    """Build a ``Generator`` backed by google-genai (Gemma vision)."""
    from google import genai
    from google.genai import types

    import os

    client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

    async def _generate(prompt: str, png: bytes) -> str:
        def _call() -> str:
            response = client.models.generate_content(
                model=model,
                contents=[
                    prompt,
                    types.Part.from_bytes(data=png, mime_type="image/png"),
                ],
                config={"max_output_tokens": max_tokens, "temperature": 0.2},
            )
            return response.text or ""

        return await asyncio.to_thread(_call)

    return _generate
