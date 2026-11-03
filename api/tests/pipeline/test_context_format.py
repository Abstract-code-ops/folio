"""Tests for the U9 context format (`build_context` only).

The protected system prompt must stay untouched, so the instruction that tells
the model how to read roles and cite passage numbers lives in the context block.
These tests pin that contract.
"""

from __future__ import annotations

from app.pipeline.qa_chain import (
    CONTEXT_INSTRUCTIONS,
    GROUNDING_SYSTEM_PROMPT,
    _outline,
    _page_label,
    build_context,
)


class _Section:
    def __init__(self, heading="Making B-trees reliable", start=82, end=84):
        self.heading = heading
        self.page_start = start
        self.page_end = end
        self.section_metadata = {"summary": "A stored summary."}


class _Passage:
    def __init__(
        self,
        content="body text",
        *,
        role=None,
        breadcrumb=None,
        note="",
        siblings=(),
        section=None,
    ):
        self.section = section or _Section()
        self.content = content
        if role is not None:
            self.role = role
        if breadcrumb is not None:
            self.breadcrumb = breadcrumb
        if note:
            self.note = note
        if siblings:
            self.siblings = tuple(siblings)


def _ctx(*passages):
    return build_context([(p, 0.1) for p in passages])


# --------------------------------------------------------------------------
# The protected prompt
# --------------------------------------------------------------------------


def test_the_instruction_is_not_in_the_system_prompt() -> None:
    assert CONTEXT_INSTRUCTIONS not in GROUNDING_SYSTEM_PROMPT
    assert "role=match" not in GROUNDING_SYSTEM_PROMPT


def test_the_instruction_is_in_the_context() -> None:
    context = _ctx(_Passage(role="match"))

    assert context.startswith("Sources and context.")
    assert "role=match are the sources" in context
    assert "tag every passage you used with its number" in context


# --------------------------------------------------------------------------
# Numbering, role and position
# --------------------------------------------------------------------------


def test_passages_are_numbered_from_one() -> None:
    context = _ctx(
        _Passage(role="match"),
        _Passage(role="match"),
        _Passage(role="context"),
    )

    assert "[1] role=match" in context
    assert "[2] role=match" in context
    assert "[3] role=context" in context


def test_header_carries_role_path_and_pages() -> None:
    context = _ctx(
        _Passage(role="match", breadcrumb="Ch 3 Storage > 3.2 B-Trees > Making it reliable")
    )

    assert (
        "[1] role=match | Ch 3 Storage > 3.2 B-Trees > Making it reliable | pp. 82-84"
        in context
    )


def test_a_single_page_is_labelled_with_p() -> None:
    assert _page_label(79, 79) == "p. 79"
    assert _page_label(82, 84) == "pp. 82-84"


def test_breadcrumb_falls_back_to_the_section_heading() -> None:
    context = _ctx(_Passage(section=_Section(heading="Bare Heading")))

    assert "| Bare Heading |" in context


def test_a_note_is_appended_when_present() -> None:
    context = _ctx(_Passage(role="context", note="opening of parent section"))

    assert "| opening of parent section" in context


def test_a_passage_without_a_role_renders_as_a_match() -> None:
    """Backward compatibility: a bare Chunk has no role attribute."""
    context = _ctx(_Passage())

    assert "[1] role=match" in context


# --------------------------------------------------------------------------
# No duplication
# --------------------------------------------------------------------------


def test_the_section_summary_is_not_printed_twice() -> None:
    """The old builder printed the summary and then the content, which doubled
    parent-summary passages."""
    passage = _Passage(content="A stored summary.", section=_Section())

    context = _ctx(passage)

    assert context.count("A stored summary.") == 1


def test_no_section_summary_line_is_emitted() -> None:
    context = _ctx(_Passage())

    assert "Section summary:" not in context


# --------------------------------------------------------------------------
# Outline
# --------------------------------------------------------------------------


def test_outline_marks_the_matched_heading() -> None:
    context = _ctx(
        _Passage(
            role="match",
            siblings=(("3.1 Intro", False), ("3.2 B-Trees", True), ("3.3 LSM", False)),
        )
    )

    assert "Outline near the matches (headings only):" in context
    assert "- 3.1 Intro | 3.2 B-Trees (matched) | 3.3 LSM" in context


def test_outline_is_not_repeated_for_identical_sibling_sets() -> None:
    siblings = (("3.1 Intro", False), ("3.2 B-Trees", True))

    context = _ctx(
        _Passage(role="match", siblings=siblings),
        _Passage(role="match", siblings=siblings),
    )

    assert context.count("Outline near the matches") == 1


def test_no_outline_when_there_are_no_siblings() -> None:
    context = _ctx(_Passage(role="match"))

    assert "Outline" not in context


def test_outline_ignores_context_passages() -> None:
    assert _outline([(_Passage(role="context", siblings=(("a", True),)), 0.1)]) == ""


# --------------------------------------------------------------------------
# Edge cases
# --------------------------------------------------------------------------


def test_no_passages_still_returns_the_instruction() -> None:
    assert build_context([]) == CONTEXT_INSTRUCTIONS


def test_content_is_preserved_verbatim() -> None:
    body = "A B-tree keeps keys sorted.\n\nIt splits on overflow."

    context = _ctx(_Passage(content=body, role="match"))

    assert body in context


def test_a_table_passage_is_tagged_with_kind() -> None:
    passage = _Passage(content="| a | b |\n| --- | --- |", role="match")
    passage.kind = "table"

    context = _ctx(passage)

    assert "kind=table" in context
    assert "| a | b |" in context


def test_a_figure_passage_is_tagged_with_kind() -> None:
    passage = _Passage(content="A binary tree diagram.", role="match")
    passage.kind = "figure"

    context = _ctx(passage)

    assert "kind=figure" in context
    assert "A binary tree diagram." in context
