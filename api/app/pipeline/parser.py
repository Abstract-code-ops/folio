"""PDF structural parsing and TOC extraction.

Opens a PDF with PyMuPDF (``fitz``), reads its table of contents, and splits
the document into a hierarchy of sections carrying ordered text blocks, real
page ranges and parent links.

Text is kept as **ordered blocks** — each with a page number, bounding box,
text and type — rather than being flattened to one string early. Later stages
need position and block boundaries: the chunker needs real paragraphs (U5), and
page-accurate citations need per-block pages (U7). ``raw_text`` is still
produced by joining the blocks so existing consumers keep working.

Nothing here touches the database.
"""

from __future__ import annotations

import logging
import math
import re
import tempfile
from pathlib import Path
from typing import Optional

import httpx
from pydantic import BaseModel, ConfigDict, Field

from app.core.config import settings

logger = logging.getLogger(__name__)

# ── Tuning ─────────────────────────────────────────────────────
# Fraction of page height at the top and bottom treated as the margin band.
_MARGIN_BAND = 0.07
# A normalised margin line must appear on at least this share of pages (and at
# least _RUNNING_TEXT_MIN_PAGES pages) before it counts as a running header.
_RUNNING_TEXT_PAGE_SHARE = 0.30
_RUNNING_TEXT_MIN_PAGES = 3
# Below this many characters a page is treated as image-only and OCR'd.
_MIN_TEXT_CHARS = 100
# OCR must recover at least this much more text before it replaces the text we
# already extracted. OCR blocks carry no geometry, so accepting them for a
# merely sparse page would destroy the block positions that heading splits and
# margin filtering depend on.
_OCR_GAIN_RATIO = 1.5
# Words split across a line break: "exam-\nple" becomes "example".
_HYPHEN_BREAK_RE = re.compile(r"([A-Za-z])-\n([a-z])")
# Bare page numbers, optionally decorated: "12", "- 12 -", "xii".
_PAGE_NUMBER_RE = re.compile(
    r"^[\s\-\u2013\u2014]*(\d{1,4}|[ivxlcdm]{1,7})[\s\-\u2013\u2014]*$",
    re.IGNORECASE,
)
# A high density of these characters means code or an equation, which must
# never be rewritten.
_CODE_CHARS = frozenset("{}[]<>=/*+$;|&\\^~")
_CODE_CHAR_RATIO = 0.02
# Slack around a heading offset, so the heading block itself is not lost to a
# rounding difference between search_for and get_text("blocks").
_HEADING_TOLERANCE = 1.0

# ── Output schemas ─────────────────────────────────────────────


class TextBlock(BaseModel):
    """One ordered block of page content."""

    page: int  # 1-based page number
    bbox: tuple[float, float, float, float]  # x0, y0, x1, y1
    text: str
    block_type: str = "text"  # "text" | "image"
    from_ocr: bool = False


class ParsedSection(BaseModel):
    """One section extracted from the PDF."""

    heading: str
    level: int  # 0=chapter, 1=section, 2=subsection, etc.
    chapter_index: int  # 0-based chapter position
    section_index: Optional[int] = None  # 0-based position within chapter
    page_start: int  # 1-based page number
    page_end: int
    word_count: int
    is_connective: bool
    raw_text: str
    blocks: list[TextBlock] = Field(default_factory=list)
    parent_index: Optional[int] = None  # index into ParseResult.sections

    model_config = ConfigDict(from_attributes=True)


class ParseResult(BaseModel):
    """Full parse output for one book."""

    title: str
    author: str
    sections: list[ParsedSection]
    total_word_count: int


# ── Classification helpers ────────────────────────────────────


def _is_connective(word_count: int) -> bool:
    """True when a section is shorter than the configured connective threshold.

    Reads ``settings.connective_word_count_threshold`` at call time rather
    than snapshotting it at import, so the value is configurable and the
    plumbing is testable.
    """
    return word_count < settings.connective_word_count_threshold


def _looks_like_code(text: str) -> bool:
    """Crude but conservative test for code or equation blocks.

    Blocks are cleaned without font information, so this errs towards treating
    anything syntax-heavy as code: rewriting a code listing to fix a hyphen is
    worse than leaving prose unfixed.
    """
    compact = re.sub(r"\s+", "", text)
    if not compact:
        return False
    symbol_ratio = sum(1 for ch in compact if ch in _CODE_CHARS) / len(compact)
    return symbol_ratio > _CODE_CHAR_RATIO


def _clean_block_text(text: str) -> str:
    """Tidy a block's text, repairing hyphenated line breaks in prose only."""
    if not text:
        return ""
    if _looks_like_code(text):
        return text.strip()
    return _HYPHEN_BREAK_RE.sub(r"\1\2", text).strip()


# ── PDF download helper ───────────────────────────────────────


async def download_pdf(storage_url: str) -> bytes:
    """Download a PDF from a Supabase Storage URL.

    Args:
        storage_url: Full URL to the PDF in Supabase Storage
            (public or signed).

    Returns:
        Raw PDF bytes.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.get(storage_url, follow_redirects=True)
        resp.raise_for_status()
        return resp.content


# ── Block extraction ──────────────────────────────────────────


def _ocr_page_blocks(page) -> list[TextBlock]:
    """Render a page and return OCR text grouped into blocks.

    One block per blank-line-separated group of OCR lines. Tesseract gives no
    reliable geometry, so these blocks carry the full page width and a zero
    top offset; they cannot participate in a same-page heading split, which is
    acceptable because a scanned page rarely carries a usable TOC entry.
    """
    page_number = page.number + 1
    try:
        import io

        import pytesseract
        from PIL import Image

        pixmap = page.get_pixmap(dpi=300)
        image = Image.open(io.BytesIO(pixmap.tobytes("png")))
        raw = pytesseract.image_to_string(image)
    except ImportError:
        logger.debug("pytesseract/PIL unavailable - no OCR for page %d", page_number)
        return []
    except Exception as exc:  # noqa: BLE001 - OCR must never break a parse
        logger.warning("OCR failed for page %d: %s", page_number, exc)
        return []

    groups = [group.strip() for group in re.split(r"\n\s*\n", raw) if group.strip()]
    if not groups:
        logger.info("  Page %d: OCR returned no text (blank page)", page_number)
        return []

    logger.info(
        "  Page %d: OCR recovered %d block(s), %d chars",
        page_number,
        len(groups),
        sum(len(group) for group in groups),
    )
    width = float(page.rect.width)
    height = float(page.rect.height)
    return [
        TextBlock(
            page=page_number,
            bbox=(0.0, 0.0, width, height),
            text=group,
            block_type="text",
            from_ocr=True,
        )
        for group in groups
    ]


def _extract_page_blocks(page) -> list[TextBlock]:
    """Extract one page as ordered text and image blocks.

    Falls back to OCR when the page yields almost no text, which covers
    image-only and scanned pages.
    """
    page_number = page.number + 1
    blocks: list[TextBlock] = []

    for item in page.get_text("blocks"):
        x0, y0, x1, y1, text, _number, block_type = item[:7]
        bbox = (float(x0), float(y0), float(x1), float(y1))
        if int(block_type) == 1:
            # Image blocks carry no text, but later stages (figures) want to
            # know they were there, so keep them typed.
            blocks.append(
                TextBlock(page=page_number, bbox=bbox, text="", block_type="image")
            )
            continue
        cleaned = _clean_block_text(text)
        if not cleaned:
            continue
        blocks.append(TextBlock(page=page_number, bbox=bbox, text=cleaned))

    text_chars = sum(len(block.text) for block in blocks if block.block_type == "text")
    if text_chars > _MIN_TEXT_CHARS:
        return blocks

    logger.info("  Page %d: regular text = %d chars - trying OCR...", page_number, text_chars)
    ocr_blocks = _ocr_page_blocks(page)
    if not ocr_blocks:
        return blocks

    ocr_chars = sum(len(block.text) for block in ocr_blocks)
    if ocr_chars > text_chars * _OCR_GAIN_RATIO:
        logger.info(
            "  Page %d: OCR recovered %d chars vs %d - using OCR blocks",
            page_number,
            ocr_chars,
            text_chars,
        )
        return ocr_blocks

    logger.info(
        "  Page %d: keeping extracted text (%d chars) over OCR (%d chars) so "
        "block geometry survives",
        page_number,
        text_chars,
        ocr_chars,
    )
    return blocks


def _drop_running_blocks(
    blocks_by_page: dict[int, list[TextBlock]],
    page_heights: dict[int, float],
) -> int:
    """Strip running headers, footers and bare page numbers from the margins.

    A margin block is dropped when its digit-stripped text repeats across a
    large share of pages, or when it is nothing but a page number. Returns how
    many blocks were dropped, so the parse log can show it.
    """
    if not blocks_by_page:
        return 0

    signature_pages: dict[str, set[int]] = {}
    for page_number, blocks in blocks_by_page.items():
        height = page_heights.get(page_number, 0.0)
        if height <= 0:
            continue
        top_limit = height * _MARGIN_BAND
        bottom_limit = height * (1.0 - _MARGIN_BAND)
        for block in blocks:
            if block.block_type != "text" or not block.text:
                continue
            if not (block.bbox[3] <= top_limit or block.bbox[1] >= bottom_limit):
                continue
            signature = re.sub(r"[\d\s]+", "", block.text).lower()
            if signature:
                signature_pages.setdefault(signature, set()).add(page_number)

    threshold = max(
        _RUNNING_TEXT_MIN_PAGES,
        math.ceil(len(blocks_by_page) * _RUNNING_TEXT_PAGE_SHARE),
    )

    dropped = 0
    for page_number, blocks in blocks_by_page.items():
        height = page_heights.get(page_number, 0.0)
        if height <= 0:
            continue
        top_limit = height * _MARGIN_BAND
        bottom_limit = height * (1.0 - _MARGIN_BAND)
        kept: list[TextBlock] = []
        for block in blocks:
            if block.block_type == "text" and block.text and (
                block.bbox[3] <= top_limit or block.bbox[1] >= bottom_limit
            ):
                if _PAGE_NUMBER_RE.match(block.text):
                    dropped += 1
                    continue
                signature = re.sub(r"[\d\s]+", "", block.text).lower()
                if signature and len(signature_pages.get(signature, set())) >= threshold:
                    dropped += 1
                    continue
            kept.append(block)
        blocks_by_page[page_number] = kept

    return dropped


# ── Section tree ──────────────────────────────────────────────


def _build_section_tree(
    toc: list[tuple[int, str, int]],
    page_count: int,
) -> list[dict]:
    """Convert a flat TOC list into section entries with page ranges.

    Args:
        toc: PyMuPDF TOC - list of ``(level, title, page_num)``.
        page_count: Total pages in the document.

    Returns:
        List of dicts with keys: level, heading, page_start, page_end.
    """
    safe_page_count = max(page_count, 1)
    if not toc:
        # No TOC - treat the entire PDF as one section.
        return [
            {
                "level": 0,
                "heading": "Full Document",
                "page_start": 1,
                "page_end": safe_page_count,
            }
        ]

    # Some PDFs report page 0 or -1 for entries with no destination; clamp so
    # a bad TOC entry cannot produce an inverted or out-of-range span.
    entries: list[tuple[int, str, int]] = []
    clamped = 0
    for level, title, page in toc:
        raw_page = page if isinstance(page, int) else 1
        safe_page = min(max(raw_page, 1), safe_page_count)
        if safe_page != raw_page:
            clamped += 1
        entries.append((level, title, safe_page))
    if clamped:
        logger.warning("Clamped %d TOC page number(s) into 1..%d", clamped, safe_page_count)

    sections: list[dict] = []
    for index, (level, title, page) in enumerate(entries):
        if index + 1 < len(entries):
            next_page = entries[index + 1][2]
            page_end = max(page - 1, next_page - 1)  # end before the next starts
            # If the next entry starts on this same page, the section still
            # owns that page; the heading split below divides it.
            if page_end < page:
                page_end = page
        else:
            page_end = safe_page_count

        sections.append(
            {
                "level": max(level - 1, 0),  # PyMuPDF levels are 1-based
                "heading": title,
                "page_start": page,
                "page_end": page_end,
            }
        )

    return sections


def _assign_hierarchy_indexes(
    sections: list[dict],
) -> list[dict]:
    """Assign chapter_index and section_index to each section based on level.

    Chapters are level-0 entries. Sections/subsections are nested under their
    parent chapter.
    """
    current_chapter = -1
    current_section = 0

    for sec in sections:
        if sec["level"] == 0:
            current_chapter += 1
            current_section = 0
            sec["chapter_index"] = current_chapter
            sec["section_index"] = None
        else:
            sec["chapter_index"] = max(current_chapter, 0)
            sec["section_index"] = current_section
            current_section += 1

    return sections


def _assign_parent_indexes(sections: list[dict]) -> list[dict]:
    """Set ``parent_index`` on each section from an ordered stack over levels.

    This replaces the old ``parent_heading`` lookup, which was computed and
    then discarded. A parent is the nearest preceding entry with a lower level.
    """
    stack: list[int] = []
    for index, section in enumerate(sections):
        while stack and sections[stack[-1]]["level"] >= section["level"]:
            stack.pop()
        section["parent_index"] = stack[-1] if stack else None
        stack.append(index)
    return sections


# ── Same-page heading splitting ───────────────────────────────


def _find_heading_offset(page, heading: str, header_limit: float) -> Optional[float]:
    """Return the top y of ``heading`` on ``page``, ignoring header-band hits."""
    try:
        hits = page.search_for(heading)
    except Exception as exc:  # noqa: BLE001 - a bad search must not fail a parse
        logger.debug("search_for failed for %r: %s", heading[:60], exc)
        return None
    for rect in hits:
        if float(rect.y0) >= header_limit:
            return float(rect.y0)
    return None


def _heading_offsets(
    doc,
    section_entries: list[dict],
    page_heights: dict[int, float],
) -> dict[int, float]:
    """Locate headings that share a page with a neighbour.

    Returns ``{section_index: top_y}`` for the entries that could be found.
    Only pages that start more than one section are searched, so a normal TOC
    costs nothing.
    """
    starts: dict[int, int] = {}
    for entry in section_entries:
        page = entry["page_start"]
        starts[page] = starts.get(page, 0) + 1
    shared_pages = {page for page, count in starts.items() if count > 1}

    if not shared_pages:
        logger.info(
            "No TOC entries share a page - using whole-page slicing "
            "(heading search skipped)"
        )
        return {}

    offsets: dict[int, float] = {}
    for index, entry in enumerate(section_entries):
        page_number = entry["page_start"]
        if page_number not in shared_pages:
            continue
        header_limit = page_heights.get(page_number, 0.0) * _MARGIN_BAND
        try:
            page = doc.load_page(page_number - 1)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not load page %d: %s", page_number, exc)
            continue
        offset = _find_heading_offset(page, entry["heading"], header_limit)
        if offset is None:
            logger.warning(
                "Could not locate heading %r on page %d - falling back to the "
                "whole page for that section",
                entry["heading"][:60],
                page_number,
            )
            continue
        offsets[index] = offset

    total_shared = sum(starts[page] for page in shared_pages)
    logger.info(
        "Located %d/%d same-page headings across %d shared page(s)",
        len(offsets),
        total_shared,
        len(shared_pages),
    )
    return offsets


def _blocks_for_section(
    blocks_by_page: dict[int, list[TextBlock]],
    *,
    page_start: int,
    page_end: int,
    y_start: Optional[float],
    y_end: Optional[float],
) -> list[TextBlock]:
    """Collect the blocks belonging to one section.

    ``y_start`` / ``y_end`` are heading offsets on the first and last page;
    ``None`` means "take the whole page", which is the fallback whenever a
    heading could not be located.
    """
    collected: list[TextBlock] = []
    for page_number in range(page_start, page_end + 1):
        for block in blocks_by_page.get(page_number, []):
            top = block.bbox[1]
            if (
                page_number == page_start
                and y_start is not None
                and top < y_start - _HEADING_TOLERANCE
            ):
                continue
            if (
                page_number == page_end
                and y_end is not None
                and top >= y_end - _HEADING_TOLERANCE
            ):
                continue
            collected.append(block)
    return collected


# ── Document parse ────────────────────────────────────────────


def parse_document(doc) -> ParseResult:
    """Parse an open PyMuPDF document into sections with ordered blocks.

    Pure with respect to the filesystem and the database: the caller owns the
    document. This is the seam the tests drive with synthetic PDFs.
    """
    page_count = doc.page_count
    meta = doc.metadata or {}
    title = (meta.get("title") or "").strip() or "Unknown Title"
    author = (meta.get("author") or "").strip() or "Unknown Author"
    logger.info("PDF opened: %d pages", page_count)
    logger.info("PDF metadata: title=%s  author=%s", title, author)

    toc = doc.get_toc() or []
    logger.info("TOC extracted: %d entries", len(toc))

    blocks_by_page: dict[int, list[TextBlock]] = {}
    page_heights: dict[int, float] = {}
    for index in range(page_count):
        page = doc.load_page(index)
        page_heights[index + 1] = float(page.rect.height)
        blocks_by_page[index + 1] = _extract_page_blocks(page)

    total_blocks = sum(len(blocks) for blocks in blocks_by_page.values())
    logger.info("Extracted %d blocks from %d page(s)", total_blocks, page_count)

    dropped = _drop_running_blocks(blocks_by_page, page_heights)
    if dropped:
        logger.info("Dropped %d running header/footer block(s)", dropped)

    section_entries = _build_section_tree(toc, page_count)
    section_entries = _assign_hierarchy_indexes(section_entries)
    section_entries = _assign_parent_indexes(section_entries)
    logger.info("Built %d section entries from TOC", len(section_entries))

    offsets = _heading_offsets(doc, section_entries, page_heights)

    parsed_sections: list[ParsedSection] = []
    total_words = 0
    for index, entry in enumerate(section_entries):
        page_start = entry["page_start"]
        page_end = entry["page_end"]

        y_start = offsets.get(index)

        y_end: Optional[float] = None
        next_index = index + 1
        if (
            next_index < len(section_entries)
            and section_entries[next_index]["page_start"] == page_end
            and next_index in offsets
        ):
            y_end = offsets[next_index]

        blocks = _blocks_for_section(
            blocks_by_page,
            page_start=page_start,
            page_end=page_end,
            y_start=y_start,
            y_end=y_end,
        )
        raw_text = "\n\n".join(
            block.text for block in blocks if block.block_type == "text" and block.text
        )
        word_count = len(raw_text.split())
        total_words += word_count

        logger.info(
            "  Section %d/%d: %s  [pp. %d-%d]  %d words (%s)%s",
            index + 1,
            len(section_entries),
            entry["heading"][:60],
            page_start,
            page_end,
            word_count,
            "OK" if word_count > 10 else "LOW TEXT",
            "  [heading split]" if y_start is not None else "",
        )

        parsed_sections.append(
            ParsedSection(
                heading=entry["heading"],
                level=entry["level"],
                chapter_index=entry["chapter_index"],
                section_index=entry["section_index"],
                page_start=page_start,
                page_end=page_end,
                word_count=word_count,
                is_connective=_is_connective(word_count),
                raw_text=raw_text,
                blocks=blocks,
                parent_index=entry["parent_index"],
            )
        )

    logger.info(
        "Parse complete: %d sections, %d total words, %d pages",
        len(parsed_sections),
        total_words,
        page_count,
    )
    return ParseResult(
        title=title,
        author=author,
        sections=parsed_sections,
        total_word_count=total_words,
    )


async def parse_pdf(storage_url: str) -> ParseResult:
    """Full parse: download → open → :func:`parse_document`.

    Args:
        storage_url: Supabase Storage URL of the PDF.

    Returns:
        ``ParseResult`` with sections, hierarchy, blocks and raw text.
    """
    logger.info("Downloading PDF from %s ...", storage_url)
    pdf_bytes = await download_pdf(storage_url)
    logger.info("Downloaded %d bytes", len(pdf_bytes))

    import fitz  # PyMuPDF

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(pdf_bytes)
        tmp_path = tmp.name

    # Suppress MuPDF C-library stderr noise ("format error: object is not a
    # stream"). These are harmless: some PDF objects use an encoding the
    # library cannot decode.
    import os as _os

    devnull_fd = _os.open(_os.devnull, _os.O_WRONLY)
    old_stderr = _os.dup(2)
    _os.dup2(devnull_fd, 2)
    _os.close(devnull_fd)

    doc = None
    try:
        doc = fitz.open(tmp_path)
        return parse_document(doc)
    finally:
        _os.dup2(old_stderr, 2)
        _os.close(old_stderr)
        if doc is not None:
            doc.close()
        Path(tmp_path).unlink(missing_ok=True)
