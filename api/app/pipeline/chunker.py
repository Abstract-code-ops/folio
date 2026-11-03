"""Hierarchy-aware chunking of parsed sections.

Splits a section into chunks that:

- never cross a section boundary;
- keep related content together (definitions stay with their examples);
- stay at or under the configured word limit;
- carry the page range of the blocks they were built from.

When ordered text blocks are passed, a paragraph is a real block boundary
rather than a guess, very short blocks are merged into a neighbour so a
heading never becomes a chunk of its own, and each chunk knows which pages it
covers. Passing plain text still works and reproduces the previous behaviour
exactly, which is what keeps existing callers and tests unchanged.

No LLM and no external service.
"""

from __future__ import annotations

import re
from typing import Optional, Protocol, Sequence

from pydantic import BaseModel, ConfigDict

from app.core.config import settings

# A block shorter than this is merged into its neighbour, so headings, captions
# and one-line list items never become chunks of their own.
_MIN_BLOCK_WORDS = 20


class _TextBlockLike(Protocol):
    """Anything block-shaped: the parser's TextBlock satisfies this."""

    text: str
    page: int
    block_type: str


class ChunkResult(BaseModel):
    """One chunk produced by the chunker."""

    content: str
    chunk_index: int
    word_count: int
    page_start: Optional[int] = None
    page_end: Optional[int] = None
    kind: str = "text"  # "text" | "table"

    model_config = ConfigDict(from_attributes=True)


class _Piece(BaseModel):
    """An indivisible unit of text, with the pages it came from."""

    text: str
    page_start: Optional[int] = None
    page_end: Optional[int] = None
    kind: str = "text"

    @property
    def word_count(self) -> int:
        return len(self.text.split())


def chunk_section(
    raw_text: str = "",
    *,
    blocks: Sequence[_TextBlockLike] | None = None,
    max_words: int | None = None,
    overlap_blocks: int | None = None,
) -> list[ChunkResult]:
    """Split one section into chunks.

    Args:
        raw_text: Full raw text of the section. Used when ``blocks`` is None.
        blocks: Ordered text blocks from the parser. Takes precedence over
            ``raw_text`` and enables page ranges and short-block merging.
        max_words: Word limit per chunk. Defaults to
            ``settings.chunk_max_words``.
        overlap_blocks: How many trailing blocks to repeat at the start of the
            next chunk. Defaults to ``settings.chunk_overlap_blocks`` (0).

    Returns:
        Chunks ordered by position in the section.
    """
    limit = max_words or settings.chunk_max_words
    overlap = (
        overlap_blocks
        if overlap_blocks is not None
        else settings.chunk_overlap_blocks
    )

    pieces = (
        _pieces_from_blocks(blocks)
        if blocks is not None
        else _pieces_from_text(raw_text)
    )
    if not pieces:
        return []

    chunks: list[ChunkResult] = []
    current: list[_Piece] = []
    current_words = 0

    def flush() -> None:
        nonlocal current, current_words
        if not current:
            return
        chunks.append(_build_chunk(current, len(chunks)))
        if overlap > 0:
            current = current[-overlap:]
            current_words = sum(piece.word_count for piece in current)
        else:
            current = []
            current_words = 0

    for piece in pieces:
        if piece.kind == "table":
            # Atomic: a table never shares a chunk with prose; an oversized
            # table is split by rows with its header repeated.
            flush()
            for part in _split_table(piece, limit):
                chunks.append(_build_chunk([part], len(chunks)))
            continue

        if piece.word_count > limit:
            flush()
            for part in _split_oversized(piece, limit):
                chunks.append(_build_chunk([part], len(chunks)))
            continue

        if current and current_words + piece.word_count > limit:
            flush()
            if current and current_words + piece.word_count > limit:
                # The overlap seed leaves no room for this piece, so start the
                # chunk clean rather than overflow the limit.
                current = []
                current_words = 0

        current.append(piece)
        current_words += piece.word_count

    if current:
        chunks.append(_build_chunk(current, len(chunks)))

    return chunks


def _build_chunk(pieces: Sequence[_Piece], index: int) -> ChunkResult:
    """Assemble one chunk from consecutive pieces."""
    text = "\n\n".join(piece.text for piece in pieces)
    starts = [p.page_start for p in pieces if p.page_start is not None]
    ends = [p.page_end for p in pieces if p.page_end is not None]
    return ChunkResult(
        content=text,
        chunk_index=index,
        word_count=len(text.split()),
        page_start=min(starts) if starts else None,
        page_end=max(ends) if ends else None,
        kind=pieces[0].kind,
    )


def _pieces_from_text(raw_text: str) -> list[_Piece]:
    """Paragraph pieces from plain text. No page information available."""
    if not raw_text or not raw_text.strip():
        return []
    return [_Piece(text=paragraph) for paragraph in _split_paragraphs(raw_text)]


def _pieces_from_blocks(blocks: Sequence[_TextBlockLike]) -> list[_Piece]:
    """Pieces from ordered blocks. Tables stay atomic; short text merges."""
    raw: list[_Piece] = []
    for block in blocks:
        block_type = getattr(block, "block_type", "text")
        if block_type not in ("text", "table"):
            continue  # image blocks carry no text
        text = (getattr(block, "text", "") or "").strip()
        if not text:
            continue
        page = getattr(block, "page", None)
        raw.append(_Piece(text=text, page_start=page, page_end=page, kind=block_type))
    return _merge_short_pieces(raw)


def _merge_short_pieces(pieces: Sequence[_Piece]) -> list[_Piece]:
    """Attach short text pieces to a neighbour; tables are hard boundaries.

    A heading belongs with the paragraph it introduces, so short text merges
    forward (or backwards if it is last). A table never merges with prose and
    closes any pending short text before it.
    """
    merged: list[_Piece] = []
    pending: Optional[_Piece] = None

    for piece in pieces:
        if piece.kind == "table":
            if pending is not None:
                if merged and merged[-1].kind == "text":
                    merged[-1] = _join(merged[-1], pending)
                else:
                    merged.append(pending)
                pending = None
            merged.append(piece)
            continue
        if pending is not None:
            piece = _join(pending, piece)
            pending = None
        if piece.word_count < _MIN_BLOCK_WORDS:
            pending = piece
            continue
        merged.append(piece)

    if pending is not None:
        if merged and merged[-1].kind == "text":
            merged[-1] = _join(merged[-1], pending)
        else:
            merged.append(pending)

    return merged


def _join(first: _Piece, second: _Piece) -> _Piece:
    """Concatenate two pieces, keeping the widest page span."""
    starts = [p for p in (first.page_start, second.page_start) if p is not None]
    ends = [p for p in (first.page_end, second.page_end) if p is not None]
    return _Piece(
        text=f"{first.text}\n{second.text}",
        page_start=min(starts) if starts else None,
        page_end=max(ends) if ends else None,
    )


def _split_oversized(piece: _Piece, limit: int) -> list[_Piece]:
    """Break up a piece that exceeds the limit.

    Sentences first. A single sentence longer than the limit (an index run, an
    unpunctuated listing) is hard-split on words as a last resort, so no chunk
    can exceed the limit.
    """
    groups: list[str] = []
    group: list[str] = []
    group_words = 0

    for sentence in _split_sentences(piece.text):
        count = len(sentence.split())
        if count > limit:
            if group:
                groups.append(" ".join(group))
                group = []
                group_words = 0
            words = sentence.split()
            for start in range(0, len(words), limit):
                groups.append(" ".join(words[start : start + limit]))
            continue
        if group_words + count > limit and group:
            groups.append(" ".join(group))
            group = []
            group_words = 0
        group.append(sentence)
        group_words += count

    if group:
        groups.append(" ".join(group))

    return [
        _Piece(text=text, page_start=piece.page_start, page_end=piece.page_end)
        for text in groups
        if text.strip()
    ]


def _split_table(piece: _Piece, limit: int) -> list[_Piece]:
    """Split an oversized Markdown table into row batches, repeating the header.

    A table smaller than ``limit`` is returned unchanged. Otherwise the header
    and separator rows are repeated at the top of each batch so every batch is
    still a valid Markdown table.
    """
    lines = piece.text.splitlines()
    if piece.word_count <= limit or len(lines) <= 2:
        return [piece]

    header = lines[:2]
    rows = lines[2:]
    header_words = len(" ".join(header).split())

    groups: list[list[str]] = []
    group: list[str] = []
    group_words = 0
    for row in rows:
        row_words = len(row.split())
        if group and header_words + group_words + row_words > limit:
            groups.append(group)
            group = []
            group_words = 0
        group.append(row)
        group_words += row_words
    if group:
        groups.append(group)

    return [
        _Piece(
            text="\n".join(header + batch),
            page_start=piece.page_start,
            page_end=piece.page_end,
            kind="table",
        )
        for batch in groups
    ]


def _split_paragraphs(text: str) -> list[str]:
    """Split text into paragraphs on double newlines."""
    raw = re.split(r"\n\s*\n", text.strip())
    return [p.strip() for p in raw if p.strip()]


def _split_sentences(text: str) -> list[str]:
    """Split text into sentences on terminal punctuation.

    Keeps decimal points and abbreviations intact by requiring a capital
    letter or end-of-string after the delimiter.
    """
    sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z\"\'`(])", text.strip())
    return [s.strip() for s in sentences if s.strip()]
