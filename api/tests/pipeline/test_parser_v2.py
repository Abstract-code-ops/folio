"""Parser v2 tests (plan unit U4).

Every PDF here is built synthetically with PyMuPDF inside the test, so no
book text enters the repository. The cases come straight from the unit spec:
sections sharing a page, a running header repeated on every page, a
hyphenated line break, a TOC nested three levels deep, and a PDF with no TOC.
"""

from __future__ import annotations

from pathlib import Path

import fitz
import pytest

from app.pipeline import parser
from app.pipeline.parser import ParsedSection, parse_document

A4 = (595, 842)

# Every page gets this filler so it clears the parser's 100-character threshold
# and never falls into the OCR path. OCR blocks carry no geometry, and these
# tests are about geometry.
_FILLER_LINES = (
    "lorem ipsum dolor sit amet consectetur adipiscing elit sed do",
    "eiusmod tempor incididunt ut labore et dolore magna aliqua",
)


def _build_pdf(
    tmp_path: Path,
    pages: list[list[tuple[float, str]]],
    toc: list[list] | None = None,
) -> Path:
    """Write a synthetic PDF. ``pages`` is a list of ``(y, text)`` runs."""
    doc = fitz.open()
    for runs in pages:
        page = doc.new_page(width=A4[0], height=A4[1])
        for y, text in runs:
            page.insert_text((72, y), text, fontsize=11)
        for offset, line in enumerate(_FILLER_LINES):
            page.insert_text((72, 700 + offset * 14), line, fontsize=11)
    if toc is not None:
        doc.set_toc(toc)
    path = tmp_path / "synthetic.pdf"
    doc.save(str(path))
    doc.close()
    return path


def _parse(path: Path):
    doc = fitz.open(str(path))
    try:
        return parse_document(doc)
    finally:
        doc.close()


# --------------------------------------------------------------------------
# Sections sharing one page (the G8 regression)
# --------------------------------------------------------------------------


def test_sections_sharing_a_page_are_split_at_the_heading(tmp_path: Path) -> None:
    pages = [
        [
            (72, "Alpha Heading"),
            (110, "alpha body text"),
            (400, "Beta Heading"),
            (440, "beta body text"),
        ]
    ]
    toc = [[1, "Alpha Heading", 1], [1, "Beta Heading", 1]]

    result = _parse(_build_pdf(tmp_path, pages, toc))

    assert len(result.sections) == 2
    alpha, beta = result.sections

    # Before U4 both sections received the whole page, so each one's text
    # appeared in the other.
    assert "alpha body text" in alpha.raw_text
    assert "beta body text" not in alpha.raw_text
    assert "beta body text" in beta.raw_text
    assert "alpha body text" not in beta.raw_text


def test_sections_sharing_a_page_are_both_non_empty(tmp_path: Path) -> None:
    pages = [
        [
            (72, "Alpha Heading"),
            (110, "alpha body text"),
            (400, "Beta Heading"),
            (440, "beta body text"),
        ]
    ]
    toc = [[1, "Alpha Heading", 1], [1, "Beta Heading", 1]]

    result = _parse(_build_pdf(tmp_path, pages, toc))

    for section in result.sections:
        assert section.raw_text.strip(), f"{section.heading} came out empty"
        assert section.word_count > 0


def test_page_ranges_never_invert(tmp_path: Path) -> None:
    pages = [[(72, "One"), (110, "body"), (400, "Two"), (440, "more body")]]
    toc = [[1, "One", 1], [1, "Two", 1]]

    result = _parse(_build_pdf(tmp_path, pages, toc))

    for section in result.sections:
        assert section.page_start <= section.page_end
        assert section.page_start >= 1


def test_three_sections_on_one_page_each_get_their_own_text(tmp_path: Path) -> None:
    pages = [
        [
            (72, "First Part"),
            (110, "first body"),
            (300, "Second Part"),
            (340, "second body"),
            (550, "Third Part"),
            (590, "third body"),
        ]
    ]
    toc = [[1, "First Part", 1], [1, "Second Part", 1], [1, "Third Part", 1]]

    result = _parse(_build_pdf(tmp_path, pages, toc))

    assert len(result.sections) == 3
    assert "first body" in result.sections[0].raw_text
    assert "second body" not in result.sections[0].raw_text
    assert "second body" in result.sections[1].raw_text
    assert "third body" not in result.sections[1].raw_text
    assert "third body" in result.sections[2].raw_text


# --------------------------------------------------------------------------
# Running headers, footers and page numbers
# --------------------------------------------------------------------------


def test_running_header_and_page_numbers_are_dropped(tmp_path: Path) -> None:
    pages = [
        [
            (20, "A Repeating Book Title"),
            (200, f"body text on page {number}"),
            (800, str(number)),
        ]
        for number in range(1, 7)
    ]
    toc = [[1, "Whole Book", 1]]

    result = _parse(_build_pdf(tmp_path, pages, toc))

    assert len(result.sections) == 1
    text = result.sections[0].raw_text
    assert "A Repeating Book Title" not in text, "running header should be dropped"
    assert "body text on page 1" in text
    assert "body text on page 6" in text


def test_one_off_margin_text_is_kept(tmp_path: Path) -> None:
    """A margin line that appears once is content, not a running header."""
    pages = [
        [(200, "body one")],
        [(20, "A One-off Margin Note"), (200, "body two")],
    ]
    toc = [[1, "Whole Book", 1]]

    result = _parse(_build_pdf(tmp_path, pages, toc))

    assert "A One-off Margin Note" in result.sections[0].raw_text


# --------------------------------------------------------------------------
# Hyphenation
# --------------------------------------------------------------------------


def test_hyphenated_line_break_is_joined_in_prose(tmp_path: Path) -> None:
    pages = [[(72, "Book"), (200, "This is an exam-"), (214, "ple of hyphenation.")]]
    toc = [[1, "Book", 1]]

    result = _parse(_build_pdf(tmp_path, pages, toc))
    text = result.sections[0].raw_text

    assert "example" in text
    assert "exam-\nple" not in text


def test_prose_hyphenation_helper_joins_lowercase_fragments() -> None:
    assert parser._clean_block_text("an exam-\nple of this") == "an example of this"


def test_uppercase_fragment_is_not_joined() -> None:
    """A hyphen before a capital is a real compound, not a line break."""
    assert parser._clean_block_text("a well-\nKnown thing") == "a well-\nKnown thing"


def test_code_blocks_are_never_rewritten() -> None:
    code = "total-\nvalue = (a + b) / c;"

    cleaned = parser._clean_block_text(code)

    assert "total-\nvalue" in cleaned


# --------------------------------------------------------------------------
# Nesting
# --------------------------------------------------------------------------


def test_parent_index_follows_three_level_nesting(tmp_path: Path) -> None:
    pages = [
        [
            (72, "Part One Alpha"),
            (110, "part body"),
            (300, "Chapter Two Beta"),
            (340, "chapter body"),
            (550, "Section Three Gamma"),
            (590, "section body"),
        ]
    ]
    toc = [
        [1, "Part One Alpha", 1],
        [2, "Chapter Two Beta", 1],
        [3, "Section Three Gamma", 1],
    ]

    result = _parse(_build_pdf(tmp_path, pages, toc))
    sections: list[ParsedSection] = result.sections

    assert len(sections) == 3
    assert sections[0].parent_index is None
    assert sections[1].parent_index == 0
    assert sections[2].parent_index == 1
    assert [section.level for section in sections] == [0, 1, 2]


def test_sibling_closes_the_preceding_branch(tmp_path: Path) -> None:
    pages = [[(72, "One"), (110, "a"), (300, "Two"), (340, "b"), (550, "Three"), (590, "c")]]
    toc = [[1, "One", 1], [2, "Two", 1], [2, "Three", 1]]

    result = _parse(_build_pdf(tmp_path, pages, toc))
    sections = result.sections

    assert sections[0].parent_index is None
    assert sections[1].parent_index == 0
    assert sections[2].parent_index == 0, "a sibling must not nest under its predecessor"


# --------------------------------------------------------------------------
# No TOC
# --------------------------------------------------------------------------


def test_a_pdf_without_a_toc_becomes_one_section(tmp_path: Path) -> None:
    pages = [
        [(200, "first page of prose")],
        [(200, "second page of prose")],
    ]

    result = _parse(_build_pdf(tmp_path, pages, toc=None))

    assert len(result.sections) == 1
    section = result.sections[0]
    assert section.heading == "Full Document"
    assert section.page_start == 1
    assert section.page_end == 2
    assert "first page of prose" in section.raw_text
    assert "second page of prose" in section.raw_text
    assert section.parent_index is None


# --------------------------------------------------------------------------
# Blocks
# --------------------------------------------------------------------------


def test_every_block_carries_its_page_number(tmp_path: Path) -> None:
    pages = [[(200, "page one text")], [(200, "page two text")]]
    toc = [[1, "One", 1], [2, "Two", 2]]

    result = _parse(_build_pdf(tmp_path, pages, toc))

    all_blocks = [block for section in result.sections for block in section.blocks]
    assert all_blocks, "expected at least one block"
    for block in all_blocks:
        assert block.page >= 1
        assert block.page <= 2

    for section in result.sections:
        for block in section.blocks:
            assert section.page_start <= block.page <= section.page_end


def test_blocks_form_the_raw_text(tmp_path: Path) -> None:
    pages = [[(72, "Heading"), (200, "a paragraph of body text")]]
    toc = [[1, "Heading", 1]]

    result = _parse(_build_pdf(tmp_path, pages, toc))
    section = result.sections[0]

    block_texts = [b.text for b in section.blocks if b.block_type == "text" and b.text]
    assert block_texts
    for text in block_texts:
        assert text in section.raw_text


def test_no_heading_search_when_no_page_is_shared(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    pages = [[(200, "one")], [(200, "two")]]
    toc = [[1, "One", 1], [1, "Two", 2]]

    with caplog.at_level("INFO", logger=parser.__name__):
        _parse(_build_pdf(tmp_path, pages, toc))

    assert any(
        "No TOC entries share a page" in record.getMessage() for record in caplog.records
    )


def test_missing_heading_falls_back_and_warns(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A heading that cannot be found on the page must warn, not crash."""
    pages = [[(72, "Alpha Heading"), (110, "alpha body"), (400, "Beta Heading"), (440, "beta body")]]
    toc = [[1, "Alpha Heading", 1], [1, "Ghost Heading", 1]]

    with caplog.at_level("WARNING", logger=parser.__name__):
        result = _parse(_build_pdf(tmp_path, pages, toc))

    assert any(
        "Could not locate heading" in record.getMessage() for record in caplog.records
    )
    # The section still gets content rather than coming out empty.
    assert result.sections[1].raw_text.strip()


# --------------------------------------------------------------------------
# Tables -> Markdown (Unit A)
# --------------------------------------------------------------------------n


class _FakeTable:
    def __init__(self, bbox, rows):
        self.bbox = bbox
        self._rows = rows

    def extract(self):
        return self._rows


class _FakeFinder:
    def __init__(self, tables):
        self.tables = tables


class _FakePage:
    def __init__(self, number, blocks, tables):
        self.number = number
        self._blocks = blocks
        self._tables = tables

    def get_text(self, mode):
        assert mode == "blocks"
        return self._blocks

    def find_tables(self):
        return _FakeFinder(self._tables)


def test_rows_to_markdown_renders_gfm_table() -> None:
    md = parser._rows_to_markdown([["Name", "Qty"], ["Apples", "3"], [None, None]])
    lines = md.splitlines()
    assert lines[0] == "| Name | Qty |"
    assert lines[1] == "| --- | --- |"
    assert "| Apples | 3 |" in md


def test_rows_to_markdown_escapes_pipes_and_flattens_newlines() -> None:
    md = parser._rows_to_markdown([["a|b"], ["line1\nline2"]])
    assert "a\\|b" in md
    assert "line1 line2" in md


def test_extract_tables_builds_markdown_and_bbox() -> None:
    table = _FakeTable((60.0, 100.0, 410.0, 200.0), [["Name", "Qty"], ["Apples", "3"]])
    page = _FakePage(0, [], [table])

    out = parser._extract_tables(page)

    assert len(out) == 1
    bbox, md = out[0]
    assert bbox == (60.0, 100.0, 410.0, 200.0)
    assert "| Name | Qty |" in md


def test_extract_tables_is_best_effort() -> None:
    class _BoomPage:
        number = 0

        def find_tables(self):
            raise RuntimeError("nope")

    assert parser._extract_tables(_BoomPage()) == []


def test_page_blocks_add_table_and_suppress_cell_text() -> None:
    long_before = (
        "Paragraph before the table with plenty of text so OCR is not triggered. " * 2
    )
    long_after = (
        "Paragraph after the table with plenty of text so OCR is not triggered. " * 2
    )
    blocks = [
        (72.0, 40.0, 400.0, 80.0, long_before, 0, 0),
        (72.0, 110.0, 400.0, 190.0, "Cell A Cell B Cell C", 1, 0),  # inside table bbox
        (72.0, 300.0, 400.0, 340.0, long_after, 2, 0),
    ]
    table = _FakeTable((60.0, 100.0, 410.0, 200.0), [["Name", "Qty"], ["Apples", "3"]])
    page = _FakePage(0, blocks, [table])

    out = parser._extract_page_blocks(page)

    assert any(b.block_type == "table" for b in out)
    table_block = next(b for b in out if b.block_type == "table")
    assert "| Name | Qty |" in table_block.text

    text = "\n".join(b.text for b in out if b.block_type == "text")
    assert "Cell A" not in text  # suppressed: it sits inside the table
    assert "Paragraph before" in text
    assert "Paragraph after" in text

    # Reading order: the before-paragraph precedes the table block.
    before = next(b for b in out if "Paragraph before" in b.text)
    assert before.bbox[1] < table_block.bbox[1]
