"""Used-only citation tests (plan unit U10).

The contract: a citation is emitted only for a passage the answer actually
cited, and it points at the chunk's own pages when those exist.
"""

from __future__ import annotations

import logging

import pytest

from app.services.qa import (
    EXCERPT_CHARS,
    ROLE_CONTEXT,
    ROLE_MATCH,
    ContextPassage,
    build_used_citations,
)


class _Section:
    def __init__(self, heading="B-trees", start=99, end=103):
        self.heading = heading
        self.page_start = start
        self.page_end = end


def _passage(
    content="body text",
    *,
    role=ROLE_MATCH,
    page_start=None,
    page_end=None,
    chunk_index=0,
    section=None,
) -> ContextPassage:
    return ContextPassage(
        section=section or _Section(),
        content=content,
        role=role,
        chunk_index=chunk_index,
        page_start=page_start,
        page_end=page_end,
    )


def _three_matches():
    return [
        _passage("first", page_start=99, page_end=99),
        _passage("second", page_start=100, page_end=101),
        _passage("third", page_start=102, page_end=103),
    ]


# --------------------------------------------------------------------------
# Citing
# --------------------------------------------------------------------------


def test_one_tag_yields_one_citation() -> None:
    citations = build_used_citations("A B-tree keeps keys sorted [2].", _three_matches())

    assert len(citations) == 1
    assert citations[0]["passage"] == 2
    assert citations[0]["type"] == "citation"


def test_multiple_tags_yield_citations_in_answer_order() -> None:
    citations = build_used_citations("See [3] and also [1].", _three_matches())

    assert [c["passage"] for c in citations] == [3, 1]


def test_repeated_tags_are_deduplicated() -> None:
    citations = build_used_citations("[1] then [1] again and [2]", _three_matches())

    assert [c["passage"] for c in citations] == [1, 2]


def test_adjacent_tags_are_both_found() -> None:
    citations = build_used_citations("as shown [1][3]", _three_matches())

    assert [c["passage"] for c in citations] == [1, 3]


def test_out_of_range_tags_are_ignored() -> None:
    citations = build_used_citations("[1] and [99]", _three_matches())

    assert [c["passage"] for c in citations] == [1]


def test_a_cited_context_passage_is_not_a_source() -> None:
    passages = [
        _passage("match text", role=ROLE_MATCH),
        _passage("parent summary", role=ROLE_CONTEXT),
    ]

    citations = build_used_citations("see [2]", passages)

    # [2] is a context passage, so it is dropped and the fallback fires.
    assert [c["passage"] for c in citations] == [1]


# --------------------------------------------------------------------------
# Fallback
# --------------------------------------------------------------------------


def test_no_tags_falls_back_to_the_top_match_and_logs(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING, logger="app.services.qa"):
        citations = build_used_citations("An answer with no tags.", _three_matches())

    assert [c["passage"] for c in citations] == [1]
    assert any("falling back" in record.getMessage() for record in caplog.records)


def test_no_match_passages_yields_no_citations() -> None:
    passages = [_passage("summary", role=ROLE_CONTEXT)]

    assert build_used_citations("anything [1]", passages) == []


def test_empty_passage_list_yields_no_citations() -> None:
    assert build_used_citations("[1]", []) == []


# --------------------------------------------------------------------------
# Page ranges
# --------------------------------------------------------------------------


def test_chunk_pages_are_preferred_over_section_pages() -> None:
    """The acceptance criterion: a narrower range than the section."""
    passage = _passage(page_start=101, page_end=101, section=_Section(start=99, end=103))

    citation = build_used_citations("[1]", [passage])[0]

    assert (citation["page_start"], citation["page_end"]) == (101, 101)
    assert citation["page_end"] - citation["page_start"] < 103 - 99


def test_section_pages_are_used_when_the_chunk_has_none() -> None:
    passage = _passage(page_start=None, page_end=None, section=_Section(start=99, end=103))

    citation = build_used_citations("[1]", [passage])[0]

    assert (citation["page_start"], citation["page_end"]) == (99, 103)


def test_citation_carries_the_section_heading() -> None:
    passage = _passage(section=_Section(heading="Making B-trees reliable"))

    citation = build_used_citations("[1]", [passage])[0]

    assert citation["section_heading"] == "Making B-trees reliable"


# --------------------------------------------------------------------------
# Shape
# --------------------------------------------------------------------------


def test_citation_has_the_expected_keys() -> None:
    citation = build_used_citations("[1]", _three_matches())[0]

    assert set(citation) == {
        "type",
        "passage",
        "chunk_index",
        "section_heading",
        "page_start",
        "page_end",
        "excerpt",
    }


def test_excerpt_is_truncated() -> None:
    passage = _passage("word " * 200)

    citation = build_used_citations("[1]", [passage])[0]

    assert len(citation["excerpt"]) <= EXCERPT_CHARS + 3
    assert citation["excerpt"].endswith("...")


def test_short_excerpt_is_untouched() -> None:
    citation = build_used_citations("[1]", [_passage("short body")])[0]

    assert citation["excerpt"] == "short body"
