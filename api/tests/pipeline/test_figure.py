"""Tests for figure/diagram ingestion helpers (Unit F).

Pure geometry + pacing are tested with fakes; the provider and DB are not
touched. Cropping and the Gemini call are covered by injection elsewhere.
"""

from __future__ import annotations

import pytest

from app.pipeline import figure


# ── Fakes ─────────────────────────────────────────────────────


class _WH:
    def __init__(self, w, h):
        self.width = w
        self.height = h


class _DR:
    def __init__(self, x0, y0, x1, y1):
        self.x0, self.y0, self.x1, self.y1 = x0, y0, x1, y1


class _Page:
    def __init__(self, images, drawings, w=600, h=800):
        self.rect = _WH(w, h)
        self._images = images
        self._drawings = drawings

    def get_image_info(self):
        return [{"bbox": b} for b in self._images]

    def get_drawings(self):
        return [{"rect": _DR(*r)} for r in self._drawings]


class _Doc:
    def __init__(self, pages):
        self._pages = pages
        self.page_count = len(pages)

    def load_page(self, i):
        return self._pages[i]


# ── Geometry ──────────────────────────────────────────────────


def test_merge_rects_merges_within_gap() -> None:
    merged = figure._merge_rects([(0, 0, 10, 10), (15, 0, 25, 10), (100, 100, 110, 110)], gap=6)
    assert len(merged) == 2


def test_iter_figure_regions_finds_raster_and_vector_and_excludes_tables() -> None:
    page = _Page(
        images=[(100, 100, 300, 300), (10, 10, 20, 20)],  # big + tiny
        drawings=[(350, 100, 520, 260), (400, 500, 560, 650)],  # diagram + table grid
    )
    doc = _Doc([page])

    regions = figure.iter_figure_regions(
        doc,
        exclude=[(1, (390, 490, 570, 660))],  # the second drawing is a table
        min_area_ratio=0.03,
        min_side=60.0,
        gap=12.0,
    )
    boxes = [bbox for _page, bbox in regions]

    assert (100.0, 100.0, 300.0, 300.0) in boxes  # big raster image
    assert (350.0, 100.0, 520.0, 260.0) in boxes  # vector diagram
    assert (10.0, 10.0, 20.0, 20.0) not in boxes  # too small
    assert all(
        not figure._overlaps(b, (390, 490, 570, 660)) for b in boxes
    ), "table region should be excluded"


# ── Caption cleaning ─────────────────────────────────────────


def test_clean_caption_takes_last_paragraph_and_collapses() -> None:
    assert figure._clean_caption("thinking...\n\nThe figure shows a tree.") == (
        "The figure shows a tree."
    )
    assert figure._clean_caption("") == ""
    assert figure._clean_caption("a   b\nc") == "a b c"


async def test_caption_figure_uses_generator_and_cleans() -> None:
    async def gen(prompt, png):
        return "Reasoning.\n\nThe diagram shows a B-tree splitting on overflow."

    class _Pacer:
        async def acquire(self):
            return None

    out = await figure.caption_figure(
        b"png", "B-trees", "context", generator=gen, pacer=_Pacer()
    )
    assert out == "The diagram shows a B-tree splitting on overflow."


# ── Pacing ────────────────────────────────────────────────────


async def test_pacer_paces_rpm() -> None:
    clock = [0.0]
    slept: list[float] = []

    def now():
        return clock[0]

    async def sleep(seconds):
        slept.append(seconds)
        clock[0] += seconds

    pacer = figure.CaptionPacer(rpm=2, rpd=100, now=now, sleep=sleep)
    await pacer.acquire()
    await pacer.acquire()
    assert clock[0] == 0.0  # two within the window, no wait
    await pacer.acquire()  # third must wait for the window to roll
    assert slept and slept[0] >= 60


async def test_pacer_raises_when_daily_budget_spent() -> None:
    clock = [0.0]

    async def sleep(seconds):
        clock[0] += seconds

    pacer = figure.CaptionPacer(rpm=100, rpd=2, now=lambda: clock[0], sleep=sleep)
    await pacer.acquire()
    await pacer.acquire()
    with pytest.raises(figure.QuotaExhausted):
        await pacer.acquire()


async def test_generate_with_backoff_quota_on_persistent_429() -> None:
    calls: list[int] = []

    async def gen(prompt, png):
        calls.append(1)
        raise RuntimeError("429 RESOURCE_EXHAUSTED retryDelay: '1'")

    slept: list[float] = []

    async def sleep(seconds):
        slept.append(seconds)

    with pytest.raises(figure.QuotaExhausted):
        await figure.generate_with_backoff(gen, "p", b"x", sleep=sleep, max_retries=2)

    assert len(calls) == 2
    assert len(slept) == 1


async def test_generate_with_backoff_passes_through_non_rate_limit_errors() -> None:
    async def gen(prompt, png):
        raise ValueError("bad thing")

    async def sleep(seconds):
        return None

    with pytest.raises(ValueError):
        await figure.generate_with_backoff(gen, "p", b"x", sleep=sleep)
