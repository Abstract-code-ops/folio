"""Tests for note documents: blocks, links, and autosave semantics.

Uses the async SQLite session from ``conftest``. A note document never runs the
section-level similarity pass, so the Dramatiq actor is asserted *not* to be
called rather than mocked out.
"""

from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.note_block import BlockKind, BlockOrigin, NoteBlock
from app.models.note_link import LinkOrigin, LinkStatus
from app.models.note_session import NoteSession, NoteSource
from app.services.notes import (
    NoteBlockDraft,
    NoteLinkDraft,
    create_note_with_blocks,
    get_note_detail,
    list_note_sessions,
    list_notes_for_section,
    replace_note_blocks,
)


# ── Helpers ────────────────────────────────────────────────────


def _link(
    *,
    section_id: uuid.UUID | None = None,
    excerpt: str = "A B-tree keeps its keys in sorted order.",
    status: LinkStatus = LinkStatus.ACCEPTED,
) -> NoteLinkDraft:
    return NoteLinkDraft(
        section_id=section_id,
        anchor_heading_path="Storage engines > B-trees",
        page_start=79,
        page_end=80,
        excerpt=excerpt,
        origin=LinkOrigin.GENERATED,
        status=status,
    )


def _blocks() -> list[NoteBlockDraft]:
    """A heading, a paragraph and a bullet, the last two citing sections."""
    return [
        NoteBlockDraft(kind=BlockKind.HEADING, text="B-trees"),
        NoteBlockDraft(
            kind=BlockKind.PARAGRAPH,
            text="A B-tree is a balanced search tree.",
            links=[_link()],
        ),
        NoteBlockDraft(
            kind=BlockKind.BULLET,
            text="Keys stay sorted within a node.",
            links=[_link()],
        ),
    ]


# ── Creating ───────────────────────────────────────────────────


class TestCreateNoteWithBlocks:
    """create_note_with_blocks() persists the document and never queues a job."""

    @pytest.mark.asyncio
    async def test_blocks_and_links_round_trip(
        self, async_session: AsyncSession,
    ):
        user_id = uuid.uuid4()
        book_id = uuid.uuid4()

        detail = await create_note_with_blocks(
            async_session,
            user_id=user_id,
            book_id=book_id,
            blocks=_blocks(),
            source=NoteSource.AI_GENERATED,
            title="B-trees",
        )

        assert detail.title == "B-trees"
        assert [block.position for block in detail.blocks] == [0, 1, 2]
        assert [block.kind for block in detail.blocks] == [
            BlockKind.HEADING,
            BlockKind.PARAGRAPH,
            BlockKind.BULLET,
        ]
        assert detail.blocks[0].links == []
        assert len(detail.blocks[1].links) == 1
        assert detail.blocks[1].links[0].page_start == 79
        assert detail.blocks[1].links[0].status == LinkStatus.ACCEPTED

    @pytest.mark.asyncio
    async def test_no_similarity_job_is_enqueued(
        self, async_session: AsyncSession,
    ):
        """Links come from generation or the student, so the matcher is not used."""
        with patch(
            "app.workers.note_session.process_note_session.send",
            autospec=True,
        ) as mock_send:
            await create_note_with_blocks(
                async_session,
                user_id=uuid.uuid4(),
                book_id=uuid.uuid4(),
                blocks=_blocks(),
                source=NoteSource.AI_GENERATED,
            )

        mock_send.assert_not_called()

    @pytest.mark.asyncio
    async def test_raw_text_mirrors_the_blocks(
        self, async_session: AsyncSession,
    ):
        """The legacy column stays truthful so the list and the view agree."""
        detail = await create_note_with_blocks(
            async_session,
            user_id=uuid.uuid4(),
            book_id=uuid.uuid4(),
            blocks=_blocks(),
            source=NoteSource.AI_GENERATED,
        )

        stored = await async_session.get(NoteSession, detail.id)

        assert stored is not None
        assert stored.raw_text == (
            "B-trees\n\nA B-tree is a balanced search tree.\n\n"
            "Keys stay sorted within a node."
        )

    @pytest.mark.asyncio
    async def test_matched_section_count_counts_distinct_accepted_sections(
        self, async_session: AsyncSession,
    ):
        """Two accepted links to the same section count once; dismissed ones never."""
        shared = uuid.uuid4()
        dismissed = uuid.uuid4()
        blocks = [
            NoteBlockDraft(
                kind=BlockKind.PARAGRAPH,
                text="First claim.",
                links=[_link(section_id=shared)],
            ),
            NoteBlockDraft(
                kind=BlockKind.PARAGRAPH,
                text="Second claim.",
                links=[
                    _link(section_id=shared),
                    _link(section_id=dismissed, status=LinkStatus.DISMISSED),
                ],
            ),
        ]

        detail = await create_note_with_blocks(
            async_session,
            user_id=uuid.uuid4(),
            book_id=uuid.uuid4(),
            blocks=blocks,
            source=NoteSource.AI_GENERATED,
        )

        assert detail.matched_section_count == 1

    @pytest.mark.asyncio
    async def test_an_empty_note_is_allowed(
        self, async_session: AsyncSession,
    ):
        """A blank note exists before the first keystroke lands."""
        detail = await create_note_with_blocks(
            async_session,
            user_id=uuid.uuid4(),
            book_id=uuid.uuid4(),
            blocks=[],
            source=NoteSource.AI_GENERATED,
        )

        assert detail.blocks == []
        assert detail.matched_section_count == 0


# ── Reading ────────────────────────────────────────────────────


class TestGetNoteDetail:
    """get_note_detail() is the read path behind GET /notes/{id}."""

    @pytest.mark.asyncio
    async def test_unknown_note_returns_none(
        self, async_session: AsyncSession,
    ):
        assert await get_note_detail(
            async_session, user_id=uuid.uuid4(), note_id=uuid.uuid4(),
        ) is None

    @pytest.mark.asyncio
    async def test_another_users_note_returns_none(
        self, async_session: AsyncSession,
    ):
        """Ownership is not a 403: someone else's note simply does not exist."""
        owner_id = uuid.uuid4()
        detail = await create_note_with_blocks(
            async_session,
            user_id=owner_id,
            book_id=uuid.uuid4(),
            blocks=_blocks(),
            source=NoteSource.AI_GENERATED,
        )

        assert detail.id is not None
        assert await get_note_detail(
            async_session, user_id=uuid.uuid4(), note_id=detail.id,
        ) is None


# ── Backlinks ──────────────────────────────────────────────────


class TestListNotesForSection:

    @staticmethod
    async def _note(
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
        book_id: uuid.UUID,
        section_id: uuid.UUID,
        text: str = "A claim about this section.",
        status: LinkStatus = LinkStatus.ACCEPTED,
    ):
        return await create_note_with_blocks(
            session,
            user_id=user_id,
            book_id=book_id,
            source=NoteSource.PASTED,
            blocks=[
                NoteBlockDraft(
                    kind=BlockKind.PARAGRAPH,
                    text=text,
                    links=[_link(section_id=section_id, status=status)],
                )
            ],
        )

    @pytest.mark.asyncio
    async def test_only_notes_citing_that_section(
        self, async_session: AsyncSession,
    ):
        user_id = uuid.uuid4()
        book_id = uuid.uuid4()
        cited = uuid.uuid4()
        other = uuid.uuid4()
        await self._note(
            async_session, user_id=user_id, book_id=book_id,
            section_id=cited, text="About the cited section.",
        )
        await self._note(
            async_session, user_id=user_id, book_id=book_id,
            section_id=other, text="About a different section.",
        )

        result = await list_notes_for_section(
            async_session, user_id=user_id, book_id=book_id, section_id=cited,
        )

        assert result.total == 1
        assert len(result.sessions) == 1

    @pytest.mark.asyncio
    async def test_a_note_appears_once_however_many_blocks_cite_it(
        self, async_session: AsyncSession,
    ):
        user_id = uuid.uuid4()
        book_id = uuid.uuid4()
        cited = uuid.uuid4()
        await create_note_with_blocks(
            async_session,
            user_id=user_id,
            book_id=book_id,
            source=NoteSource.PASTED,
            blocks=[
                NoteBlockDraft(
                    kind=BlockKind.PARAGRAPH,
                    text="First claim.",
                    links=[_link(section_id=cited)],
                ),
                NoteBlockDraft(
                    kind=BlockKind.BULLET,
                    text="Second claim.",
                    links=[_link(section_id=cited)],
                ),
            ],
        )

        result = await list_notes_for_section(
            async_session, user_id=user_id, book_id=book_id, section_id=cited,
        )

        assert result.total == 1

    @pytest.mark.asyncio
    async def test_dismissed_links_are_not_citations(
        self, async_session: AsyncSession,
    ):
        user_id = uuid.uuid4()
        book_id = uuid.uuid4()
        cited = uuid.uuid4()
        await self._note(
            async_session, user_id=user_id, book_id=book_id,
            section_id=cited, status=LinkStatus.DISMISSED,
        )

        result = await list_notes_for_section(
            async_session, user_id=user_id, book_id=book_id, section_id=cited,
        )

        assert result.total == 0

    @pytest.mark.asyncio
    async def test_scoped_to_the_caller(
        self, async_session: AsyncSession,
    ):
        book_id = uuid.uuid4()
        cited = uuid.uuid4()
        await self._note(
            async_session, user_id=uuid.uuid4(), book_id=book_id,
            section_id=cited,
        )

        result = await list_notes_for_section(
            async_session, user_id=uuid.uuid4(), book_id=book_id, section_id=cited,
        )

        assert result.total == 0


# ── Autosave ───────────────────────────────────────────────────


class TestReplaceNoteBlocks:
    """replace_note_blocks() diffs by block id and preserves surviving links."""

    @pytest.mark.asyncio
    async def test_editing_text_keeps_the_block_and_its_link(
        self, async_session: AsyncSession,
    ):
        """The point of linking blocks instead of offsets: an edit keeps the chip."""
        user_id = uuid.uuid4()
        created = await create_note_with_blocks(
            async_session,
            user_id=user_id,
            book_id=uuid.uuid4(),
            blocks=_blocks(),
            source=NoteSource.AI_GENERATED,
        )
        paragraph = created.blocks[1]
        link_id = paragraph.links[0].id

        edited = [
            NoteBlockDraft(
                id=created.blocks[0].id,
                kind=BlockKind.HEADING,
                text="B-trees",
            ),
            NoteBlockDraft(
                id=paragraph.id,
                kind=BlockKind.PARAGRAPH,
                text="A B-tree is a self-balancing search tree, rewritten.",
            ),
            NoteBlockDraft(
                id=created.blocks[2].id,
                kind=BlockKind.BULLET,
                text=created.blocks[2].text,
            ),
        ]

        saved = await replace_note_blocks(
            async_session, user_id=user_id, note_id=created.id, blocks=edited,
        )

        assert saved.blocks[1].id == paragraph.id
        assert saved.blocks[1].text.endswith("rewritten.")
        assert len(saved.blocks[1].links) == 1
        assert saved.blocks[1].links[0].id == link_id

    @pytest.mark.asyncio
    async def test_removed_blocks_are_deleted(
        self, async_session: AsyncSession,
    ):
        user_id = uuid.uuid4()
        created = await create_note_with_blocks(
            async_session,
            user_id=user_id,
            book_id=uuid.uuid4(),
            blocks=_blocks(),
            source=NoteSource.AI_GENERATED,
        )

        saved = await replace_note_blocks(
            async_session,
            user_id=user_id,
            note_id=created.id,
            blocks=[
                NoteBlockDraft(
                    id=created.blocks[0].id,
                    kind=BlockKind.HEADING,
                    text="B-trees",
                )
            ],
        )

        assert len(saved.blocks) == 1
        remaining = await async_session.get(NoteBlock, created.blocks[1].id)
        assert remaining is None

    @pytest.mark.asyncio
    async def test_a_block_without_an_id_is_inserted(
        self, async_session: AsyncSession,
    ):
        user_id = uuid.uuid4()
        created = await create_note_with_blocks(
            async_session,
            user_id=user_id,
            book_id=uuid.uuid4(),
            blocks=_blocks(),
            source=NoteSource.AI_GENERATED,
        )

        saved = await replace_note_blocks(
            async_session,
            user_id=user_id,
            note_id=created.id,
            blocks=[
                NoteBlockDraft(
                    id=created.blocks[0].id,
                    kind=BlockKind.HEADING,
                    text="B-trees",
                ),
                NoteBlockDraft(
                    kind=BlockKind.PARAGRAPH,
                    text="A brand new paragraph.",
                    origin=BlockOrigin.TYPED,
                ),
            ],
        )

        assert [block.position for block in saved.blocks] == [0, 1]
        assert saved.blocks[1].text == "A brand new paragraph."
        assert saved.blocks[1].id != created.blocks[1].id

    @pytest.mark.asyncio
    async def test_editing_keeps_the_original_origin(
        self, async_session: AsyncSession,
    ):
        """origin records where the text came from; an edit does not change it.

        Without this, every autosave rewrote an AI-generated block as typed.
        """
        user_id = uuid.uuid4()
        created = await create_note_with_blocks(
            async_session,
            user_id=user_id,
            book_id=uuid.uuid4(),
            blocks=[
                NoteBlockDraft(
                    kind=BlockKind.PARAGRAPH,
                    text="Generated text.",
                    origin=BlockOrigin.AI,
                )
            ],
            source=NoteSource.AI_GENERATED,
        )
        assert created.blocks[0].origin == BlockOrigin.AI

        saved = await replace_note_blocks(
            async_session,
            user_id=user_id,
            note_id=created.id,
            blocks=[
                NoteBlockDraft(
                    id=created.blocks[0].id,
                    kind=BlockKind.PARAGRAPH,
                    text="Generated text, now edited.",
                    origin=BlockOrigin.TYPED,
                )
            ],
        )

        assert saved.blocks[0].origin == BlockOrigin.AI
        assert saved.blocks[0].text.endswith("now edited.")

    @pytest.mark.asyncio
    async def test_a_block_named_twice_does_not_swallow_text(
        self, async_session: AsyncSession,
    ):
        """Regression for splitting a paragraph in the editor.

        Pressing Enter mid-paragraph used to hand the same block id to both
        halves. Honouring both meant the second write overwrote the first, so
        the text before the cursor vanished on save.
        """
        user_id = uuid.uuid4()
        created = await create_note_with_blocks(
            async_session,
            user_id=user_id,
            book_id=uuid.uuid4(),
            blocks=[
                NoteBlockDraft(
                    kind=BlockKind.PARAGRAPH,
                    text="The whole paragraph.",
                )
            ],
            source=NoteSource.PASTED,
        )
        block_id = created.blocks[0].id

        saved = await replace_note_blocks(
            async_session,
            user_id=user_id,
            note_id=created.id,
            blocks=[
                NoteBlockDraft(
                    id=block_id,
                    kind=BlockKind.PARAGRAPH,
                    text="Text before the cursor.",
                ),
                NoteBlockDraft(
                    id=block_id,
                    kind=BlockKind.PARAGRAPH,
                    text="Text after the cursor.",
                ),
            ],
        )

        texts = [block.text for block in saved.blocks]
        assert texts == ["Text before the cursor.", "Text after the cursor."]
        assert saved.blocks[0].id == block_id
        assert saved.blocks[1].id != block_id

    @pytest.mark.asyncio
    async def test_another_users_note_is_not_writable(
        self, async_session: AsyncSession,
    ):
        created = await create_note_with_blocks(
            async_session,
            user_id=uuid.uuid4(),
            book_id=uuid.uuid4(),
            blocks=_blocks(),
            source=NoteSource.AI_GENERATED,
        )

        with pytest.raises(ValueError):
            await replace_note_blocks(
                async_session,
                user_id=uuid.uuid4(),
                note_id=created.id,
                blocks=_blocks(),
            )


class TestSectionIdsOnSummary:
    """The list carries cited section ids, so backlinks need no second request."""

    @pytest.mark.asyncio
    async def test_cited_sections_are_attached(
        self, async_session: AsyncSession,
    ):
        user_id = uuid.uuid4()
        book_id = uuid.uuid4()
        cited = uuid.uuid4()
        await create_note_with_blocks(
            async_session,
            user_id=user_id,
            book_id=book_id,
            source=NoteSource.PASTED,
            blocks=[
                NoteBlockDraft(
                    kind=BlockKind.PARAGRAPH,
                    text="A claim.",
                    links=[_link(section_id=cited)],
                )
            ],
        )

        result = await list_note_sessions(
            async_session, user_id=user_id, book_id=book_id,
        )

        assert result.sessions[0].section_ids == [cited]
        # A short page proves there is nothing after it, so no count query runs.
        assert result.total == 1

    @pytest.mark.asyncio
    async def test_dismissed_links_are_not_attached(
        self, async_session: AsyncSession,
    ):
        user_id = uuid.uuid4()
        book_id = uuid.uuid4()
        await create_note_with_blocks(
            async_session,
            user_id=user_id,
            book_id=book_id,
            source=NoteSource.PASTED,
            blocks=[
                NoteBlockDraft(
                    kind=BlockKind.PARAGRAPH,
                    text="A claim.",
                    links=[
                        _link(
                            section_id=uuid.uuid4(),
                            status=LinkStatus.DISMISSED,
                        )
                    ],
                )
            ],
        )

        result = await list_note_sessions(
            async_session, user_id=user_id, book_id=book_id,
        )

        assert result.sessions[0].section_ids == []
