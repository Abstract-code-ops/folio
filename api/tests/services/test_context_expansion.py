"""Context expansion tests (plan unit U8, steps 4 and 5).

Neighbour and parent passages are additive: they must never change the matched
chunks, never duplicate a match, and never invent a summary that isn't stored.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.models.book import Book
from app.models.chunk import Chunk
from app.models.section import Section
from app.services.qa import ROLE_CONTEXT, ROLE_MATCH, expand_context


async def _seed(db) -> dict:
    book = Book(title="T", author="A", storage_url="https://example.test/b.pdf")
    db.add(book)
    await db.flush()

    parent = Section(
        book_id=book.id,
        chapter_index=0,
        section_index=None,
        level=0,
        heading="Chapter One",
        page_start=1,
        page_end=10,
        word_count=500,
        is_connective=False,
        raw_text="chapter text",
        section_metadata={"summary": "This chapter covers the basics."},
    )
    db.add(parent)
    await db.flush()

    child = Section(
        book_id=book.id,
        chapter_index=0,
        section_index=0,
        level=1,
        heading="Section One",
        page_start=2,
        page_end=4,
        word_count=300,
        is_connective=False,
        raw_text="section text",
        section_metadata={"summary": "A section summary."},
        parent_section_id=parent.id,
    )
    db.add(child)
    await db.flush()

    for index, page in enumerate((2, 3, 4)):
        db.add(
            Chunk(
                section_id=child.id,
                chunk_index=index,
                content=f"chunk number {index}",
                page_start=page,
                page_end=page,
                embedding=[0.1, 0.2],
                embed_version=2,
            )
        )
    await db.flush()

    chunks = (
        (
            await db.execute(
                select(Chunk)
                .where(Chunk.section_id == child.id)
                .options(joinedload(Chunk.section))
                .order_by(Chunk.chunk_index)
            )
        )
        .unique()
        .scalars()
        .all()
    )
    return {"book": book, "parent": parent, "child": child, "chunks": chunks}


async def test_no_expansion_returns_only_matches(async_session) -> None:
    seeded = await _seed(async_session)
    hits = [(seeded["chunks"][1], 0.2)]

    passages = await expand_context(
        async_session, hits, include_neighbours=False, include_parent_summary=False
    )

    assert len(passages) == 1
    assert passages[0].role == ROLE_MATCH
    assert passages[0].distance == 0.2


async def test_neighbours_are_added_on_both_sides(async_session) -> None:
    seeded = await _seed(async_session)
    hits = [(seeded["chunks"][1], 0.2)]

    passages = await expand_context(
        async_session, hits, include_neighbours=True, include_parent_summary=False
    )

    context = [p for p in passages if p.role == ROLE_CONTEXT]
    assert len(context) == 2
    assert {p.chunk_index for p in context} == {0, 2}
    assert passages[0].role == ROLE_MATCH


async def test_a_neighbour_that_is_also_a_match_is_not_duplicated(async_session) -> None:
    seeded = await _seed(async_session)
    hits = [(seeded["chunks"][0], 0.1), (seeded["chunks"][1], 0.2)]

    passages = await expand_context(
        async_session, hits, include_neighbours=True, include_parent_summary=False
    )

    chunk_indexes = [p.chunk_index for p in passages if p.role == ROLE_CONTEXT]
    assert chunk_indexes == [2], "index 0 is already a match and must not repeat"


async def test_parent_summary_is_added_as_context(async_session) -> None:
    seeded = await _seed(async_session)
    hits = [(seeded["chunks"][1], 0.2)]

    passages = await expand_context(
        async_session, hits, include_neighbours=False, include_parent_summary=True
    )

    parent_passages = [
        p
        for p in passages
        if p.role == ROLE_CONTEXT and p.section.id == seeded["parent"].id
    ]
    assert len(parent_passages) == 1
    assert parent_passages[0].content == "This chapter covers the basics."
    assert parent_passages[0].chunk_index is None


async def test_parent_without_a_summary_adds_nothing(async_session) -> None:
    seeded = await _seed(async_session)
    seeded["parent"].section_metadata = {}
    await async_session.flush()
    hits = [(seeded["chunks"][1], 0.2)]

    passages = await expand_context(
        async_session, hits, include_neighbours=False, include_parent_summary=True
    )

    assert all(p.role == ROLE_MATCH for p in passages)


async def test_both_expansions_together(async_session) -> None:
    seeded = await _seed(async_session)
    hits = [(seeded["chunks"][1], 0.2)]

    passages = await expand_context(
        async_session, hits, include_neighbours=True, include_parent_summary=True
    )

    assert len(passages) == 4  # 1 match + 2 neighbours + 1 parent summary
    assert [p.role for p in passages].count(ROLE_CONTEXT) == 3


async def test_empty_hits_expand_to_nothing(async_session) -> None:
    await _seed(async_session)

    passages = await expand_context(
        async_session, [], include_neighbours=True, include_parent_summary=True
    )

    assert passages == []


async def test_expansion_does_not_change_the_matched_content(async_session) -> None:
    """Citations are built from matches, so their content must stay untouched."""
    seeded = await _seed(async_session)
    original = seeded["chunks"][1].content
    hits = [(seeded["chunks"][1], 0.2)]

    passages = await expand_context(
        async_session, hits, include_neighbours=True, include_parent_summary=True
    )

    matches = [p for p in passages if p.role == ROLE_MATCH]
    assert matches[0].content == original
