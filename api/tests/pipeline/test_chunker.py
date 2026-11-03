"""Chunker v2 tests (plan unit U5).

Blocks come from the parser in production; here they are tiny stubs, because
the chunker only needs ``text``, ``page`` and ``block_type``.
"""

from __future__ import annotations

import pytest

from app.core.config import settings
from app.pipeline.chunker import ChunkResult, chunk_section


class _Block:
    """Minimal stand-in for parser.TextBlock."""

    def __init__(self, text: str, page: int, block_type: str = "text") -> None:
        self.text = text
        self.page = page
        self.block_type = block_type


def _words(count: int, prefix: str = "word") -> str:
    return " ".join(f"{prefix}{i}" for i in range(count))


@pytest.fixture(autouse=True)
def default_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "chunk_max_words", 750)
    monkeypatch.setattr(settings, "chunk_overlap_blocks", 0)


# --------------------------------------------------------------------------
# The plain-text path must not change behaviour
# --------------------------------------------------------------------------


def test_plain_text_produces_one_chunk_for_small_input() -> None:
    raw = "First paragraph of the section.\n\nSecond paragraph of the section."

    chunks = chunk_section(raw)

    assert len(chunks) == 1
    assert chunks[0].content == raw
    assert chunks[0].word_count == len(raw.split())
    assert chunks[0].chunk_index == 0


def test_plain_text_has_no_page_range() -> None:
    chunks = chunk_section("Some text without blocks.\n\nAnd more text.")

    assert all(chunk.page_start is None for chunk in chunks)
    assert all(chunk.page_end is None for chunk in chunks)


def test_plain_text_chunks_never_exceed_the_default_limit() -> None:
    paragraphs = [_words(100, prefix=f"p{i}_") for i in range(10)]

    chunks = chunk_section("\n\n".join(paragraphs))

    assert len(chunks) > 1
    assert all(chunk.word_count <= 750 for chunk in chunks)


def test_empty_input_returns_no_chunks() -> None:
    assert chunk_section("") == []
    assert chunk_section("   \n\n  ") == []
    assert chunk_section(blocks=[]) == []


def test_chunk_indexes_are_sequential() -> None:
    paragraphs = [_words(200, prefix=f"p{i}_") for i in range(5)]

    chunks = chunk_section("\n\n".join(paragraphs))

    assert [chunk.chunk_index for chunk in chunks] == list(range(len(chunks)))


# --------------------------------------------------------------------------
# Page ranges from blocks
# --------------------------------------------------------------------------


def test_blocks_produce_the_chunk_page_range() -> None:
    blocks = [
        _Block(_words(100, "a"), page=10),
        _Block(_words(100, "b"), page=11),
        _Block(_words(100, "c"), page=12),
    ]

    chunks = chunk_section(blocks=blocks)

    assert len(chunks) == 1
    assert chunks[0].page_start == 10
    assert chunks[0].page_end == 12


def test_split_chunks_carry_their_own_page_range() -> None:
    blocks = [
        _Block(_words(100, "a"), page=10),
        _Block(_words(100, "b"), page=11),
        _Block(_words(100, "c"), page=12),
    ]

    chunks = chunk_section(blocks=blocks, max_words=250)

    assert len(chunks) == 2
    assert (chunks[0].page_start, chunks[0].page_end) == (10, 11)
    assert (chunks[1].page_start, chunks[1].page_end) == (12, 12)


def test_chunks_only_contain_their_own_blocks() -> None:
    first = [_Block(_words(100, f"one{i}_"), page=i) for i in (1, 2)]
    second = [_Block(_words(100, f"two{i}_"), page=i) for i in (3, 4)]

    first_chunks = chunk_section(blocks=first, max_words=150)
    second_chunks = chunk_section(blocks=second, max_words=150)

    assert all("two" not in chunk.content for chunk in first_chunks)
    assert all("one" not in chunk.content for chunk in second_chunks)


# --------------------------------------------------------------------------
# Short-block merging
# --------------------------------------------------------------------------


def test_a_heading_is_merged_into_the_paragraph_it_introduces() -> None:
    blocks = [
        _Block("B-trees", page=99),
        _Block(_words(60, "body"), page=99),
    ]

    chunks = chunk_section(blocks=blocks)

    assert len(chunks) == 1
    assert chunks[0].content.startswith("B-trees")
    assert "body0" in chunks[0].content


def test_a_trailing_short_block_is_merged_backwards() -> None:
    blocks = [
        _Block(_words(60, "body"), page=5),
        _Block("The end.", page=6),
    ]

    chunks = chunk_section(blocks=blocks)

    assert len(chunks) == 1
    assert chunks[0].content.endswith("The end.")
    assert (chunks[0].page_start, chunks[0].page_end) == (5, 6)


def test_consecutive_short_blocks_all_land_in_one_chunk() -> None:
    blocks = [
        _Block("Chapter 3", page=40),
        _Block("Storage and Retrieval", page=40),
        _Block(_words(60, "body"), page=40),
    ]

    chunks = chunk_section(blocks=blocks)

    assert len(chunks) == 1
    assert "Chapter 3" in chunks[0].content
    assert "Storage and Retrieval" in chunks[0].content


def test_image_blocks_are_ignored() -> None:
    blocks = [
        _Block("A real paragraph of text here.", page=1),
        _Block("", page=1, block_type="image"),
        _Block(_words(60, "body"), page=1),
    ]

    chunks = chunk_section(blocks=blocks)

    assert len(chunks) == 1
    assert chunks[0].word_count > 0


# --------------------------------------------------------------------------
# Oversized input
# --------------------------------------------------------------------------


def test_a_single_overlong_sentence_is_hard_split() -> None:
    # No terminal punctuation, so the sentence splitter cannot help.
    blocks = [_Block(_words(400, "run"), page=1)]

    chunks = chunk_section(blocks=blocks, max_words=100)

    assert len(chunks) == 4
    assert all(chunk.word_count <= 100 for chunk in chunks)


def test_a_long_paragraph_is_split_on_sentences() -> None:
    sentences = [f"This is sentence number {i} of the example." for i in range(60)]
    blocks = [_Block(" ".join(sentences), page=1)]

    chunks = chunk_section(blocks=blocks, max_words=100)

    assert len(chunks) > 1
    assert all(chunk.word_count <= 100 for chunk in chunks)


def test_no_chunk_exceeds_the_configured_limit() -> None:
    blocks = [
        _Block(_words(300, f"b{i}_"), page=i)
        for i in range(1, 6)
    ] + [_Block(_words(900, "long"), page=6)]

    chunks = chunk_section(blocks=blocks, max_words=250)

    assert chunks
    assert all(chunk.word_count <= 250 for chunk in chunks)


# --------------------------------------------------------------------------
# Settings and overlap
# --------------------------------------------------------------------------


def test_max_words_defaults_to_the_setting(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "chunk_max_words", 50)
    paragraphs = [_words(40, prefix=f"p{i}_") for i in range(4)]

    chunks = chunk_section("\n\n".join(paragraphs))

    assert all(chunk.word_count <= 50 for chunk in chunks)
    assert len(chunks) == 4


def test_overlap_repeats_the_last_block_of_the_previous_chunk() -> None:
    blocks = [
        _Block(_words(60, "one"), page=1),
        _Block(_words(60, "two"), page=2),
        _Block(_words(60, "three"), page=3),
    ]

    chunks = chunk_section(blocks=blocks, max_words=150, overlap_blocks=1)

    assert len(chunks) == 2
    # The second chunk starts by repeating the block that closed the first.
    assert "two0" in chunks[0].content
    assert chunks[1].content.startswith("two")


def test_overlap_is_off_by_default() -> None:
    blocks = [
        _Block(_words(60, "one"), page=1),
        _Block(_words(60, "two"), page=2),
            _Block(_words(60, "three"), page=3),
    ]

    chunks = chunk_section(blocks=blocks, max_words=150)

    assert len(chunks) == 2
    assert not chunks[1].content.startswith("two")


def test_overlap_never_pushes_a_chunk_over_the_limit() -> None:
    blocks = [
        _Block(_words(140, "big"), page=1),
        _Block(_words(140, "next"), page=2),
    ]

    chunks = chunk_section(blocks=blocks, max_words=150, overlap_blocks=1)

    assert all(chunk.word_count <= 150 for chunk in chunks)


def test_chunk_result_exposes_page_fields() -> None:
    chunk = chunk_section(blocks=[_Block(_words(60, "body"), page=7)])[0]

    assert isinstance(chunk, ChunkResult)
    assert chunk.page_start == 7
    assert chunk.page_end == 7


# --------------------------------------------------------------------------
# Tables (Unit B)
# --------------------------------------------------------------------------


def _table_md(rows: int) -> str:
    lines = ["| Shard | Range |", "| --- | --- |"]
    for i in range(rows):
        lines.append(f"| shard{i} | range{i} |")
    return "\n".join(lines)


def test_table_block_becomes_one_table_chunk() -> None:
    prose = "Intro paragraph about sharding that is long enough to stand alone. " * 3
    blocks = [
        _Block(prose, page=98),
        _Block(_table_md(4), page=98, block_type="table"),
    ]

    chunks = chunk_section(blocks=blocks)

    table_chunks = [c for c in chunks if c.kind == "table"]
    assert len(table_chunks) == 1
    assert table_chunks[0].content.startswith("| Shard | Range |")
    assert table_chunks[0].page_start == 98


def test_table_is_not_merged_with_prose() -> None:
    blocks = [
        _Block(_words(60, "before"), page=1),
        _Block(_table_md(3), page=1, block_type="table"),
        _Block(_words(60, "after"), page=1),
    ]

    chunks = chunk_section(blocks=blocks)

    assert [c.kind for c in chunks].count("table") == 1
    table_chunk = next(c for c in chunks if c.kind == "table")
    assert "before0" not in table_chunk.content
    assert "after0" not in table_chunk.content


def test_oversized_table_is_split_by_rows_with_header_repeated() -> None:
    blocks = [_Block(_table_md(40), page=5, block_type="table")]

    chunks = chunk_section(blocks=blocks, max_words=30)

    table_chunks = [c for c in chunks if c.kind == "table"]
    assert len(table_chunks) > 1
    for chunk in table_chunks:
        assert chunk.content.startswith("| Shard | Range |\n| --- | --- |")
        assert chunk.word_count <= 30


def test_plain_text_chunks_are_kind_text() -> None:
    chunks = chunk_section("A paragraph.\n\nAnother paragraph.")
    assert all(chunk.kind == "text" for chunk in chunks)
