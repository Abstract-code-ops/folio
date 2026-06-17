"""Hierarchy-aware chunking of parsed sections.

Splits section text into chunks that:
- Never cross section boundaries.
- Keep related content together (definitions with examples).
- Target a maximum size (~750 words / ~1000 tokens per chunk).

The chunker operates on plain text paragraphs — it does not use
the LLM or any external service.
"""

from __future__ import annotations

import re
from typing import Optional

from pydantic import BaseModel, ConfigDict

# Target: ~1000 tokens ≈ ~750 words per chunk
# Paragraphs are grouped into chunks up to this limit.
MAX_CHUNK_WORDS = 750


class ChunkResult(BaseModel):
    """One chunk produced by the chunker."""

    content: str
    chunk_index: int
    word_count: int

    model_config = ConfigDict(from_attributes=True)


def chunk_section(raw_text: str) -> list[ChunkResult]:
    """Split a section's raw text into hierarchy-aware chunks.

    Chunking strategy:
    1. Split on paragraph boundaries (``\\n\\n``).
    2. Group consecutive paragraphs into a chunk until the word
       count approaches ``MAX_CHUNK_WORDS``.
    3. Never split a paragraph across two chunks.
    4. If a single paragraph exceeds ``MAX_CHUNK_WORDS``, split it
       on sentence boundaries (``.``, ``!``, ``?``) instead.

    Args:
        raw_text: Full raw text of one section.

    Returns:
        List of ``ChunkResult`` objects, ordered by position in
        the section.
    """
    if not raw_text or not raw_text.strip():
        return []

    paragraphs = _split_paragraphs(raw_text)
    chunks: list[ChunkResult] = []
    current_pieces: list[str] = []
    current_word_count = 0
    chunk_idx = 0

    for para in paragraphs:
        para_words = len(para.split())

        if not para.strip():
            continue

        # If this single paragraph exceeds the max, split it on sentences
        if para_words > MAX_CHUNK_WORDS:
            # Flush any accumulated paragraphs first
            if current_pieces:
                text = "\n\n".join(current_pieces)
                chunks.append(ChunkResult(
                    content=text,
                    chunk_index=chunk_idx,
                    word_count=current_word_count,
                ))
                chunk_idx += 1
                current_pieces = []
                current_word_count = 0

            # Split the oversized paragraph on sentences
            sentences = _split_sentences(para)
            sent_group: list[str] = []
            sent_count = 0
            for sent in sentences:
                sent_words = len(sent.split())
                if sent_count + sent_words > MAX_CHUNK_WORDS and sent_group:
                    text = " ".join(sent_group)
                    chunks.append(ChunkResult(
                        content=text,
                        chunk_index=chunk_idx,
                        word_count=sent_count,
                    ))
                    chunk_idx += 1
                    sent_group = []
                    sent_count = 0
                sent_group.append(sent)
                sent_count += sent_words

            if sent_group:
                text = " ".join(sent_group)
                chunks.append(ChunkResult(
                    content=text,
                    chunk_index=chunk_idx,
                    word_count=sent_count,
                ))
                chunk_idx += 1

            continue

        # Normal case: add paragraph to current chunk
        if current_word_count + para_words > MAX_CHUNK_WORDS and current_pieces:
            # Flush current chunk
            text = "\n\n".join(current_pieces)
            chunks.append(ChunkResult(
                content=text,
                chunk_index=chunk_idx,
                word_count=current_word_count,
            ))
            chunk_idx += 1
            current_pieces = []
            current_word_count = 0

        current_pieces.append(para)
        current_word_count += para_words

    # Flush remaining
    if current_pieces:
        text = "\n\n".join(current_pieces)
        chunks.append(ChunkResult(
            content=text,
            chunk_index=chunk_idx,
            word_count=current_word_count,
        ))

    return chunks


def _split_paragraphs(text: str) -> list[str]:
    """Split text into paragraphs on double newlines."""
    raw = re.split(r"\n\s*\n", text.strip())
    return [p.strip() for p in raw if p.strip()]


def _split_sentences(text: str) -> list[str]:
    """Split text into sentences on terminal punctuation.

    Keeps decimal points and abbreviations intact by requiring
    a capital letter or end-of-string after the delimiter.
    """
    sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z\"\'`(])", text.strip())
    return [s.strip() for s in sentences if s.strip()]