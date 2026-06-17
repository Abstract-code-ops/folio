"""PDF structural parsing and TOC extraction.

Uses ``pymupdf4llm`` (via PyMuPDF/fitz) to open a PDF, extract its
table of contents, and split the document into a hierarchy of sections
with page ranges and raw text.

Supports download from Supabase Storage URLs.
"""

from __future__ import annotations

import logging
import re
import tempfile
import uuid
from pathlib import Path
from typing import Optional

import httpx
from pydantic import BaseModel, ConfigDict

logger = logging.getLogger(__name__)

# Word count threshold for connective sections (matches settings default)
CONNECTIVE_THRESHOLD = 150


# ── Output schemas ─────────────────────────────────────────────


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
    parent_heading: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class ParseResult(BaseModel):
    """Full parse output for one book."""

    title: str
    author: str
    sections: list[ParsedSection]
    total_word_count: int


# ── PDF download helper ────────────────────────────────────────


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


# ── Parser ─────────────────────────────────────────────────────


def _build_section_tree(
    toc: list[tuple[int, str, int]],
    page_count: int,
) -> list[dict]:
    """Convert a flat TOC list into hierarchical section entries with page ranges.

    Args:
        toc: PyMuPDF TOC — list of ``(level, title, page_num)``.
        page_count: Total pages in the document.

    Returns:
        List of dicts with keys: level, heading, page_start, page_end.
    """
    if not toc:
        # No TOC — treat the entire PDF as one section
        return [{"level": 0, "heading": "Full Document", "page_start": 1, "page_end": page_count}]

    sections = []
    for i, (level, title, page) in enumerate(toc):
        # Page range: from this entry's page to the next entry's page (or end of doc)
        if i + 1 < len(toc):
            next_page = toc[i + 1][2]
            page_end = max(page - 1, next_page - 1)  # end before next section starts
            # If the next TOC entry starts on the same page, this section is just that page
            if page_end < page:
                page_end = page
        else:
            page_end = page_count

        sections.append({
            "level": level - 1,  # PyMuPDF uses 1-based levels; normalise to 0-based
            "heading": title,
            "page_start": page,
            "page_end": page_end,
        })

    return sections


def _extract_page_text(doc, page_num: int) -> str:
    """Extract text from a single PDF page.

    Args:
        doc: Fitz Document object.
        page_num: 0-based page index.

    Returns:
        Plain text of the page.
    """
    page = doc.load_page(page_num)
    text = page.get_text("text")
    return text.strip()


def _assign_hierarchy_indexes(
    sections: list[dict],
) -> list[dict]:
    """Assign chapter_index and section_index to each section based on level.

    Chapters are level-0 entries. Sections/Subsections are nested
    under their parent chapter.
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


async def parse_pdf(storage_url: str) -> ParseResult:
    """Full parse: download → extract TOC → build sections → extract text.

    Args:
        storage_url: Supabase Storage URL of the PDF.

    Returns:
        ``ParseResult`` with all sections, their hierarchy, and raw text.
    """
    pdf_bytes = await download_pdf(storage_url)

    import fitz  # PyMuPDF — bundled with pymupdf4llm

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(pdf_bytes)
        tmp_path = tmp.name

    try:
        doc = fitz.open(tmp_path)
        page_count = doc.page_count

        # Extract metadata
        meta = doc.metadata or {}
        title = meta.get("title", "").strip() or "Unknown Title"
        author = meta.get("author", "").strip() or "Unknown Author"

        # Extract TOC
        toc = doc.get_toc()  # list of (level, title, page)

        # Build section tree with page ranges
        section_entries = _build_section_tree(toc, page_count)

        # Assign hierarchy indexes
        section_entries = _assign_hierarchy_indexes(section_entries)

        # Extract raw text per section
        parsed_sections: list[ParsedSection] = []
        total_words = 0

        for entry in section_entries:
            # Collect text from all pages in the section's range
            page_texts: list[str] = []
            for p in range(entry["page_start"] - 1, entry["page_end"]):
                if 0 <= p < page_count:
                    page_texts.append(_extract_page_text(doc, p))

            raw_text = "\n\n".join(page_texts)
            word_count = len(raw_text.split()) if raw_text.strip() else 0
            total_words += word_count

            # Determine parent section heading
            parent_heading = None
            level = entry["level"]
            if level > 0:
                # Find the closest ancestor with level - 1
                idx = section_entries.index(entry)
                for j in range(idx - 1, -1, -1):
                    if section_entries[j]["level"] < level:
                        parent_heading = section_entries[j]["heading"]
                        break

            parsed_sections.append(
                ParsedSection(
                    heading=entry["heading"],
                    level=entry["level"],
                    chapter_index=entry["chapter_index"],
                    section_index=entry["section_index"],
                    page_start=entry["page_start"],
                    page_end=entry["page_end"],
                    word_count=word_count,
                    is_connective=word_count < CONNECTIVE_THRESHOLD,
                    raw_text=raw_text,
                    parent_heading=parent_heading,
                )
            )

        return ParseResult(
            title=title,
            author=author,
            sections=parsed_sections,
            total_word_count=total_words,
        )

    finally:
        doc.close()
        Path(tmp_path).unlink(missing_ok=True)