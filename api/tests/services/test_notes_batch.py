"""Tests for the batched write-behind upsert (POST /notes/batch).

Runs on the async SQLite fixture like the other note service tests. The
dialect-aware ``_upsert_insert`` picks SQLite's ``ON CONFLICT`` here and
Postgres's in production, so these exercise the real code path.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.note_block import BlockKind, NoteBlock
from app.models.note_link import LinkOrigin, LinkStatus, NoteLink
from app.models.note_session import NoteSession, NoteSource
from app.services.notes import (
    NoteBatchBlock,
    NoteBatchLink,
    NoteBatchNote,
    NoteBlockDraft,
    create_note_with_blocks,
    upsert_notes_batch,
)


def _link(
    *,
    section_id: uuid.UUID | None = None,
    excerpt: str = "A B-tree keeps keys sorted.",
    status: LinkStatus = LinkStatus.ACCEPTED,
) -> NoteBatchLink:
    return NoteBatchLink(
        id=uuid.uuid4(),
        section_id=section_id,
        anchor_heading_path="Storage > B-trees",
        page_start=79,
        page_end=80,
        excerpt=excerpt,
        status=status,
        origin=LinkOrigin.MANUAL,
    )


def _note(
    *,
    id: uuid.UUID | None = None,
    book_id: uuid.UUID | None = None,
    blocks: list[NoteBatchBlock] | None = None,
) -> NoteBatchNote:
    return NoteBatchNote(
        id=id or uuid.uuid4(),
        book_id=book_id or uuid.uuid4(),
        title="Batch",
        source=NoteSource.PASTED,
        blocks=blocks or [],
    )


async def _blocks(session: AsyncSession, note_id: uuid.UUID) -> list[NoteBlock]:
    rows = await session.execute(select(NoteBlock).where(NoteBlock.note_id == note_id))
    return list(rows.scalars().all())


async def _links(session: AsyncSession, block_id: uuid.UUID) -> list[NoteLink]:
    rows = await session.execute(select(NoteLink).where(NoteLink.block_id == block_id))
    return list(rows.scalars().all())


class TestUpsertNotesBatch:

    @pytest.mark.asyncio
    async def test_inserts_new_note_with_client_ids(self, async_session: AsyncSession):
        """Client-generated ids ARE the row ids (idempotent for outbox replay)."""
        user_id = uuid.uuid4()
        note = _note(
            blocks=[
                NoteBatchBlock(
                    id=uuid.uuid4(),
                    kind=BlockKind.PARAGRAPH,
                    text="Hello",
                    links=[_link(section_id=uuid.uuid4())],
                )
            ]
        )

        synced = await upsert_notes_batch(async_session, user_id=user_id, notes=[note])

        assert [s[0] for s in synced] == [note.id]
        assert await async_session.get(NoteSession, note.id) is not None
        assert len(await _blocks(async_session, note.id)) == 1

    @pytest.mark.asyncio
    async def test_is_idempotent_on_replay(self, async_session: AsyncSession):
        user_id = uuid.uuid4()
        note = _note(
            blocks=[NoteBatchBlock(id=uuid.uuid4(), kind=BlockKind.PARAGRAPH, text="Hello")]
        )

        await upsert_notes_batch(async_session, user_id=user_id, notes=[note])
        await upsert_notes_batch(async_session, user_id=user_id, notes=[note])

        assert len(await _blocks(async_session, note.id)) == 1

    @pytest.mark.asyncio
    async def test_updates_text_and_drops_removed_blocks(self, async_session: AsyncSession):
        user_id = uuid.uuid4()
        keeper = NoteBatchBlock(id=uuid.uuid4(), kind=BlockKind.PARAGRAPH, text="keep")
        doomed = NoteBatchBlock(id=uuid.uuid4(), kind=BlockKind.PARAGRAPH, text="drop me")
        note = _note(blocks=[keeper, doomed])
        await upsert_notes_batch(async_session, user_id=user_id, notes=[note])

        keeper2 = NoteBatchBlock(id=keeper.id, kind=BlockKind.PARAGRAPH, text="keep, edited")
        note2 = _note(id=note.id, book_id=note.book_id, blocks=[keeper2])
        await upsert_notes_batch(async_session, user_id=user_id, notes=[note2])

        rows = await _blocks(async_session, note.id)
        assert [b.id for b in rows] == [keeper.id]
        assert rows[0].text == "keep, edited"

    @pytest.mark.asyncio
    async def test_preserves_links_on_surviving_block(self, async_session: AsyncSession):
        user_id = uuid.uuid4()
        link = _link(section_id=uuid.uuid4())
        block = NoteBatchBlock(
            id=uuid.uuid4(), kind=BlockKind.PARAGRAPH, text="claim", links=[link]
        )
        note = _note(blocks=[block])
        await upsert_notes_batch(async_session, user_id=user_id, notes=[note])

        block2 = NoteBatchBlock(
            id=block.id, kind=BlockKind.PARAGRAPH, text="claim, rewritten", links=[link]
        )
        note2 = _note(id=note.id, book_id=note.book_id, blocks=[block2])
        await upsert_notes_batch(async_session, user_id=user_id, notes=[note2])

        stored = await _links(async_session, block.id)
        assert [l.id for l in stored] == [link.id]

    @pytest.mark.asyncio
    async def test_matched_section_count_computed_from_payload(
        self, async_session: AsyncSession
    ):
        shared = uuid.uuid4()
        note = _note(
            blocks=[
                NoteBatchBlock(
                    id=uuid.uuid4(),
                    kind=BlockKind.PARAGRAPH,
                    text="a",
                    links=[_link(section_id=shared)],
                ),
                NoteBatchBlock(
                    id=uuid.uuid4(),
                    kind=BlockKind.PARAGRAPH,
                    text="b",
                    links=[_link(section_id=shared), _link(section_id=uuid.uuid4())],
                ),
            ]
        )
        await upsert_notes_batch(async_session, user_id=uuid.uuid4(), notes=[note])

        # Two distinct accepted sections (shared + one) -> 2.
        detail = await async_session.get(NoteSession, note.id)
        assert detail.matched_section_count == 2

    @pytest.mark.asyncio
    async def test_refuses_another_users_note(self, async_session: AsyncSession):
        created = await create_note_with_blocks(
            async_session,
            user_id=uuid.uuid4(),
            book_id=uuid.uuid4(),
            blocks=[NoteBlockDraft(kind=BlockKind.PARAGRAPH, text="owned")],
            source=NoteSource.PASTED,
        )
        hijack = NoteBatchNote(
            id=created.id,
            book_id=created.book_id,
            source=NoteSource.PASTED,
            blocks=[NoteBatchBlock(id=uuid.uuid4(), kind=BlockKind.PARAGRAPH, text="hacked")],
        )

        synced = await upsert_notes_batch(async_session, user_id=uuid.uuid4(), notes=[hijack])

        assert synced == []
        stored = await async_session.get(NoteSession, created.id)
        assert stored.raw_text == "owned"

    @pytest.mark.asyncio
    async def test_empty_batch_is_a_noop(self, async_session: AsyncSession):
        assert await upsert_notes_batch(async_session, user_id=uuid.uuid4(), notes=[]) == []

    @pytest.mark.asyncio
    async def test_deletes_owned_note_and_its_children(self, async_session: AsyncSession):
        user_id = uuid.uuid4()
        block = NoteBatchBlock(
            id=uuid.uuid4(), kind=BlockKind.PARAGRAPH, text="x", links=[_link(section_id=uuid.uuid4())]
        )
        note = _note(blocks=[block])
        await upsert_notes_batch(async_session, user_id=user_id, notes=[note])

        await upsert_notes_batch(
            async_session, user_id=user_id, notes=[], deleted=[note.id]
        )

        assert await async_session.get(NoteSession, note.id) is None
        assert await _blocks(async_session, note.id) == []
        assert await _links(async_session, block.id) == []

    @pytest.mark.asyncio
    async def test_delete_ignores_another_users_note(self, async_session: AsyncSession):
        created = await create_note_with_blocks(
            async_session,
            user_id=uuid.uuid4(),
            book_id=uuid.uuid4(),
            blocks=[NoteBlockDraft(kind=BlockKind.PARAGRAPH, text="owned")],
            source=NoteSource.PASTED,
        )

        await upsert_notes_batch(
            async_session, user_id=uuid.uuid4(), notes=[], deleted=[created.id]
        )

        assert await async_session.get(NoteSession, created.id) is not None
