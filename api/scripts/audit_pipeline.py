"""Read-only audit of the ingestion pipeline (plan unit U0).

Prints a Markdown report describing what the parsed data actually looks
like, before any pipeline change is made. Every number in the report is
a real database value; nothing is sampled or estimated.

Read-only by construction: all queries are SELECTs, there are no writes,
no model calls, and no network access.

What it measures (per book), matching the U0 checklist:

1. sections with ``word_count == 0``, empty ``raw_text``, or an inverted
   page range (``page_end < page_start``);
2. how many consecutive TOC entries share a ``page_start`` (the
   "several sections start on one page" problem that decides whether
   parser v2 needs ``search_for`` heading splitting);
3. sections whose ``section_metadata.summary`` is empty (the silent
   metadata failure), as a count and a list of positions;
4. the count and share of ``is_connective`` sections, and how many of
   those still carry definitions, equations, or examples (this defines
   "connective" for retrieval v2);
5. the chunk word-count distribution and chunks per section;
6. whether any ``parent_section_id`` is set (expected: none).

Usage (inside the api container, with the database reachable)::

    docker exec folio-api-1 python3 /app/scripts/audit_pipeline.py
    docker exec folio-api-1 python3 /app/scripts/audit_pipeline.py > docs/pipeline-audit.md

The script is deliberately runnable as a plain file: it puts the project
root on ``sys.path`` itself, so it does not depend on ``PYTHONPATH``.
"""

from __future__ import annotations

import math
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

# Running ``python3 /app/scripts/audit_pipeline.py`` sets sys.path[0] to
# the scripts directory; add the project root so ``app.*`` imports resolve.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.core.db import SyncSessionLocal  # noqa: E402
from app.models.book import Book  # noqa: E402
from app.models.chunk import Chunk  # noqa: E402
from app.models.section import Section  # noqa: E402
# Mirrors the chunker's configured limit, read from config so the report
# cannot drift from the real setting.
MAX_CHUNK_WORDS = settings.chunk_max_words

# How many items to list per finding before summarising the remainder.
LIST_CAP = 25


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------


def _percentile(values: Sequence[int], p: float) -> int | None:
    """Nearest-rank percentile of an integer sample."""
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, math.ceil(p * len(ordered)))
    return ordered[rank - 1]


def _dist(values: Sequence[int]) -> str:
    """One-line min / median / p90 / max description of a sample."""
    if not values:
        return "n/a (no values)"
    return (
        f"min={min(values)} median={statistics.median(values):g} "
        f"p90={_percentile(values, 0.90)} max={max(values)}"
    )


def _doc_order(section: Section) -> tuple[int, int, int, int]:
    """Sort key reproducing parse/TOC order.

    ``chapter_index`` first, then ``section_index`` (chapters carry
    ``None`` and sort before their children), then page, then level.
    """
    return (
        section.chapter_index,
        -1 if section.section_index is None else section.section_index,
        section.page_start,
        section.level,
    )


def _meta(section: Section) -> dict[str, Any]:
    """Return ``section_metadata`` as a dict, tolerating NULL."""
    return section.section_metadata or {}


def _has_items(section: Section, key: str) -> bool:
    """True when ``section_metadata[key]`` is a non-empty list."""
    value = _meta(section).get(key)
    return isinstance(value, list) and len(value) > 0


def _label(section: Section, position: int) -> str:
    """Compact, human-readable label for a section."""
    heading = section.heading if len(section.heading) <= 60 else section.heading[:57] + "..."
    return (
        f"#{position} ch{section.chapter_index}/sec{section.section_index} "
        f"L{section.level} pp.{section.page_start}-{section.page_end} "
        f'"{heading}"'
    )


def _summary_is_empty(section: Section) -> bool:
    """True when the extracted summary is missing or blank."""
    summary = _meta(section).get("summary")
    return not (isinstance(summary, str) and summary.strip())


# --------------------------------------------------------------------------
# Per-book audit
# --------------------------------------------------------------------------


def audit_book(db: Session, book: Book) -> dict[str, Any]:
    """Collect every U0 metric for a single book. Read-only."""
    sections = list(db.scalars(select(Section).where(Section.book_id == book.id)))
    sections.sort(key=_doc_order)
    positions = {id(s): i for i, s in enumerate(sections, start=1)}
    section_by_id = {s.id: s for s in sections}

    section_ids = [s.id for s in sections]
    chunks: list[Chunk] = []
    if section_ids:
        chunks = list(
            db.scalars(select(Chunk).where(Chunk.section_id.in_(section_ids)))
        )

    # 1. Degenerate sections.
    zero_words = [s for s in sections if (s.word_count or 0) == 0]
    empty_text = [s for s in sections if not (s.raw_text and s.raw_text.strip())]
    inverted = [s for s in sections if s.page_end < s.page_start]

    # 2. Same-page TOC pairs (consecutive sections sharing a page_start).
    same_page_pairs = [
        (positions[id(a)], positions[id(b)], a.page_start)
        for a, b in zip(sections, sections[1:])
        if a.page_start == b.page_start
    ]

    # 3. Silent metadata failure.
    empty_summary = [s for s in sections if _summary_is_empty(s)]

    # 4. Connective sections and whether they carry real content.
    connective = [s for s in sections if s.is_connective]
    connective_with_content = [
        s
        for s in connective
        if _has_items(s, "definitions")
        or _has_items(s, "equations")
        or _has_items(s, "examples")
    ]
    connective_share = (len(connective) / len(sections) * 100.0) if sections else 0.0

    # 5. Chunks.
    chunk_words = [len((c.content or "").split()) for c in chunks]
    oversize_chunks = [
        (c, len((c.content or "").split()))
        for c in chunks
        if len((c.content or "").split()) > MAX_CHUNK_WORDS
    ]
    per_section: dict[Any, int] = {}
    for c in chunks:
        per_section[c.section_id] = per_section.get(c.section_id, 0) + 1
    sections_without_chunks = [s for s in sections if s.id not in per_section]

    # 6. Hierarchy.
    parent_links = [s for s in sections if s.parent_section_id is not None]

    return {
        "book": book,
        "total_sections": len(sections),
        "total_words": sum((s.word_count or 0) for s in sections),
        "zero_words": zero_words,
        "empty_text": empty_text,
        "inverted": inverted,
        "same_page_pairs": same_page_pairs,
        "empty_summary": empty_summary,
        "connective": connective,
        "connective_with_content": connective_with_content,
        "connective_share": connective_share,
        "chunk_count": len(chunks),
        "chunk_words": chunk_words,
        "oversize_chunks": oversize_chunks,
        "section_by_id": section_by_id,
        "per_section_counts": list(per_section.values()),
        "sections_without_chunks": sections_without_chunks,
        "parent_links": parent_links,
        "positions": positions,
    }


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------


def _render_list(items: list[str]) -> list[str]:
    """Render a capped bullet list."""
    if not items:
        return ["  - none"]
    lines = [f"  - {item}" for item in items[:LIST_CAP]]
    if len(items) > LIST_CAP:
        lines.append(f"  - ... and {len(items) - LIST_CAP} more")
    return lines


def render_markdown(books_data: list[dict[str, Any]], snapshot: dict[str, int]) -> str:
    """Render the full report as Markdown."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    out: list[str] = []
    out.append("# Pipeline audit")
    out.append("")
    out.append(f"Generated: {now}")
    out.append("")
    out.append(
        "Read-only snapshot of the live database, produced by "
        "`api/scripts/audit_pipeline.py` (plan unit U0). Every number below "
        "is a direct database value."
    )
    out.append("")
    out.append("## Snapshot")
    out.append("")
    out.append("| Books | Sections | Chunks |")
    out.append("| --- | --- | --- |")
    out.append(
        f"| {snapshot['books']} | {snapshot['sections']} | {snapshot['chunks']} |"
    )
    out.append("")

    # Summary table across all books.
    out.append("## Summary per book")
    out.append("")
    out.append(
        "| Book | Status | Sections | Words | Empty text | Zero words | "
        "Inverted pages | Same-page pairs | Empty summaries | Connective | "
        "Connective w/ content | Chunks | Sections w/o chunks | Parent links |"
    )
    out.append(
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | "
        "--- | --- | --- | --- |"
    )
    for d in books_data:
        book = d["book"]
        out.append(
            "| {title} | {status} | {secs} | {words} | {empty} | {zero} | "
            "{inv} | {same} | {nosum} | {conn} ({share:.0f}%) | {connc} | "
            "{chunks} | {nochunk} | {parents} |".format(
                title=book.title,
                status=book.ingestion_status.value
                if hasattr(book.ingestion_status, "value")
                else book.ingestion_status,
                secs=d["total_sections"],
                words=d["total_words"],
                empty=len(d["empty_text"]),
                zero=len(d["zero_words"]),
                inv=len(d["inverted"]),
                same=len(d["same_page_pairs"]),
                nosum=len(d["empty_summary"]),
                conn=len(d["connective"]),
                share=d["connective_share"],
                connc=len(d["connective_with_content"]),
                chunks=d["chunk_count"],
                nochunk=len(d["sections_without_chunks"]),
                parents=len(d["parent_links"]),
            )
        )
    out.append("")

    # Per-book detail.
    for d in books_data:
        book = d["book"]
        out.append(f"## {book.title}")
        out.append("")
        out.append(f"- id: `{book.id}`")
        out.append(
            f"- status: "
            f"{book.ingestion_status.value if hasattr(book.ingestion_status, 'value') else book.ingestion_status}"
        )
        out.append(
            f"- sections: {d['total_sections']} | words: {d['total_words']} | "
            f"chunks: {d['chunk_count']}"
        )
        out.append("")

        out.append("### Degenerate sections")
        out.append("")
        out.append(f"- empty `raw_text`: {len(d['empty_text'])}")
        out.extend(_render_list([_label(s, d["positions"][id(s)]) for s in d["empty_text"]]))
        out.append(f"- `word_count == 0`: {len(d['zero_words'])}")
        out.extend(_render_list([_label(s, d["positions"][id(s)]) for s in d["zero_words"]]))
        out.append(f"- inverted page range (`page_end < page_start`): {len(d['inverted'])}")
        out.extend(_render_list([_label(s, d["positions"][id(s)]) for s in d["inverted"]]))
        out.append("")

        out.append("### Same-page TOC entries")
        out.append("")
        out.append(
            "Consecutive parsed sections that begin on the same page. Non-zero "
            "means the flat page-range model is collapsing several sections "
            "into one page slice (decides the U4 heading-split sub-step)."
        )
        out.append("")
        out.append(f"- pairs sharing `page_start`: {len(d['same_page_pairs'])}")
        out.extend(
            _render_list(
                [
                    f"#{a} and #{b} both start on p.{page}"
                    for a, b, page in d["same_page_pairs"]
                ]
            )
        )
        out.append("")

        out.append("### Silent metadata failure")
        out.append("")
        out.append(f"- sections with empty `summary`: {len(d['empty_summary'])}")
        out.extend(
            _render_list(
                [_label(s, d["positions"][id(s)]) for s in d["empty_summary"]]
            )
        )
        out.append("")

        out.append("### Connective sections")
        out.append("")
        out.append(
            f"- connective: {len(d['connective'])} "
            f"({d['connective_share']:.1f}% of sections)"
        )
        out.append(
            f"- connective but carrying definitions/equations/examples: "
            f"{len(d['connective_with_content'])}"
        )
        out.extend(
            _render_list(
                [
                    _label(s, d["positions"][id(s)])
                    for s in d["connective_with_content"]
                ]
            )
        )
        out.append("")

        out.append("### Chunks")
        out.append("")
        out.append(f"- chunk words: {_dist(d['chunk_words'])}")
        out.append(f"- chunks per section: {_dist(d['per_section_counts'])}")
        out.append(
            f"- chunks over the {MAX_CHUNK_WORDS}-word maximum: "
            f"{len(d['oversize_chunks'])}"
        )
        out.extend(
            _render_list(
                [
                    "section {h!r} chunk {i} = {w} words".format(
                        h=(
                            d["section_by_id"][c.section_id].heading[:50]
                            if c.section_id in d["section_by_id"]
                            else "<unknown>"
                        ),
                        i=c.chunk_index,
                        w=w,
                    )
                    for c, w in d["oversize_chunks"]
                ]
            )
        )
        out.append(f"- sections with no chunks: {len(d['sections_without_chunks'])}")
        out.extend(
            _render_list(
                [
                    _label(s, d["positions"][id(s)])
                    for s in d["sections_without_chunks"]
                ]
            )
        )
        out.append("")

        out.append("### Hierarchy")
        out.append("")
        out.append(
            f"- sections with `parent_section_id` set: {len(d['parent_links'])} "
            f"(expected 0 before the parser v2 work)"
        )
        out.append("")

    # Decisions this audit feeds, per the U0 goal.
    out.append("## What this audit decides")
    out.append("")
    any_same_page = any(d["same_page_pairs"] for d in books_data)
    total_same_page = sum(len(d["same_page_pairs"]) for d in books_data)
    any_parents = any(d["parent_links"] for d in books_data)
    total_empty_summary = sum(len(d["empty_summary"]) for d in books_data)
    total_connective = sum(len(d["connective"]) for d in books_data)
    total_connective_content = sum(
        len(d["connective_with_content"]) for d in books_data
    )
    total_oversize = sum(len(d["oversize_chunks"]) for d in books_data)
    not_ingested = [d["book"] for d in books_data if d["total_sections"] == 0]

    out.append(
        f"- Same-page TOC entries: {total_same_page} pair(s) across all books. "
        f"Page ranges come from the TOC, so this stays non-zero by design - U4 "
        f"splits the text at the heading, it does not change the page span."
    )
    out.append(
        f"- Connective definition (U8 item 6): {total_connective} sections are "
        f"flagged connective and {total_connective_content} of those carry "
        f"definitions, equations, or examples. A short L1 heading whose content "
        f"lives in child subsections also counts as short, so treat the flag as "
        f"'little text of its own' rather than 'connective passage'."
    )
    if total_oversize:
        out.append(
            f"- Chunk size: {total_oversize} chunk(s) exceed the "
            f"{MAX_CHUNK_WORDS}-word maximum. These came from the sentence "
            f"splitter, which needs terminal punctuation followed by a capital."
        )
    else:
        out.append(
            f"- Chunk size: no chunk exceeds the {MAX_CHUNK_WORDS}-word maximum."
        )
    if total_empty_summary:
        out.append(
            f"- Empty summaries: {total_empty_summary} section(s). Check whether "
            f"they are front matter with nothing to summarise (normal) or a "
            f"cluster at the start of a book (one truncated metadata batch)."
        )
    else:
        out.append("- Empty summaries: none.")
    out.append(
        f"- Hierarchy: parent_section_id is "
        f"{'populated' if any_parents else 'empty everywhere'}"
        f"{' as intended for parser v2 output' if any_parents else ' - books ingested before parser v2 still need a re-ingest'}."
    )
    if not_ingested:
        names = ", ".join('"' + b.title + '"' for b in not_ingested)
        out.append(
            f"- Not ingested (0 sections, real zeros): {names}. These books "
            f"need ingestion before they can be audited further."
        )
    out.append("")
    return "\n".join(out)


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------


def main() -> int:
    """Run the audit and print the Markdown report to stdout."""
    with SyncSessionLocal() as db:
        books = list(db.scalars(select(Book).order_by(Book.title)))
        books_data: list[dict[str, Any]] = [audit_book(db, b) for b in books]

        snapshot = {
            "books": len(books),
            "sections": sum(d["total_sections"] for d in books_data),
            "chunks": sum(d["chunk_count"] for d in books_data),
        }

    if not books:
        print("# Pipeline audit")
        print("")
        print(f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
        print("")
        print("No books in the database. Nothing to audit.")
        return 0

    print(render_markdown(books_data, snapshot))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
