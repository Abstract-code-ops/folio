"""Tests for the v2 embedding input strings (plan unit U7).

These pin the exact strings handed to nomic-embed-text, because a silent change
here would degrade retrieval without breaking anything visibly.
"""

from __future__ import annotations

from app.pipeline.embed_inputs import (
    DOCUMENT_PREFIX,
    QUERY_PREFIX,
    SECTION_OPENING_WORDS,
    build_breadcrumb,
    chunk_embed_text,
    query_embed_text,
    section_embed_text,
)


def test_build_breadcrumb_joins_with_the_separator() -> None:
    assert build_breadcrumb(["Part I", "Chapter 2", "B-trees"]) == (
        "Part I > Chapter 2 > B-trees"
    )


def test_build_breadcrumb_skips_blank_parts() -> None:
    assert build_breadcrumb(["Part I", "", "  ", "B-trees"]) == "Part I > B-trees"


def test_build_breadcrumb_of_nothing_is_empty() -> None:
    assert build_breadcrumb([]) == ""
    assert build_breadcrumb(["", "   "]) == ""


# --------------------------------------------------------------------------
# Chunks
# --------------------------------------------------------------------------


def test_chunk_input_is_prefix_breadcrumb_then_content() -> None:
    result = chunk_embed_text("Part I > B-trees", "A B-tree keeps keys sorted.")

    assert result == (
        "search_document: Part I > B-trees\nA B-tree keeps keys sorted."
    )


def test_chunk_input_without_breadcrumb_is_prefix_then_content() -> None:
    assert chunk_embed_text("", "Just the content.") == (
        "search_document: Just the content."
    )


def test_the_prefix_constant_matches_what_the_strings_use() -> None:
    assert chunk_embed_text("H", "body").startswith(DOCUMENT_PREFIX + " ")


# --------------------------------------------------------------------------
# Sections
# --------------------------------------------------------------------------


def test_section_input_has_breadcrumb_summary_concepts_and_opening() -> None:
    result = section_embed_text(
        breadcrumb="Part I > B-trees",
        summary="A summary of the section.",
        concepts=["B-tree", "LSM-tree"],
        raw_text="The opening text of the section.",
    )

    assert result == (
        "search_document: Part I > B-trees\n"
        "A summary of the section.\n"
        "Concepts: B-tree, LSM-tree\n"
        "The opening text of the section."
    )


def test_section_input_falls_back_when_the_summary_is_empty() -> None:
    result = section_embed_text(
        breadcrumb="Part I > Cover",
        summary="",
        concepts=["ignored"],
        raw_text="Opening text only.",
    )

    assert result == "search_document: Part I > Cover\nOpening text only."
    assert "Concepts:" not in result


def test_section_input_omits_the_concepts_line_when_there_are_none() -> None:
    result = section_embed_text(
        breadcrumb="H",
        summary="A summary.",
        concepts=[],
        raw_text="Body.",
    )

    assert "Concepts:" not in result
    assert result == "search_document: H\nA summary.\nBody."


def test_section_input_caps_the_opening_text() -> None:
    raw_text = " ".join(f"w{i}" for i in range(SECTION_OPENING_WORDS + 500))

    result = section_embed_text(
        breadcrumb="H", summary="S", concepts=[], raw_text=raw_text
    )

    opening = result.split("S\n", 1)[1]
    assert len(opening.split()) == SECTION_OPENING_WORDS


# --------------------------------------------------------------------------
# Queries (U8)
# --------------------------------------------------------------------------


def test_query_input_is_bare_when_the_flag_is_off() -> None:
    assert query_embed_text("what is a b-tree", prefixed=False) == "what is a b-tree"


def test_query_input_carries_the_query_prefix_when_on() -> None:
    assert query_embed_text("what is a b-tree", prefixed=True) == (
        "search_query: what is a b-tree"
    )


def test_query_prefix_differs_from_the_document_prefix() -> None:
    assert QUERY_PREFIX != DOCUMENT_PREFIX


def test_query_input_is_stripped() -> None:
    assert query_embed_text("  spaces  ", prefixed=False) == "spaces"


def test_empty_query_is_empty_either_way() -> None:
    assert query_embed_text("", prefixed=False) == ""
    assert query_embed_text("", prefixed=True) == "search_query: "
