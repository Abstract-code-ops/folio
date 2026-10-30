"""Note session submission, note documents, and note generation logic.

Three flows:
  1. **Pasted notes** -- creates a ``NoteSession`` record and enqueues a
     Dramatiq background job to run the section-level similarity pass. Returns
     immediately with session + job IDs. This is the legacy path: it matches
     whole sections, not blocks.
  2. **AI-generated notes** -- streams note generation section-by-section via
     the LLM pipeline (chapter range).
  3. **Note documents** -- a note is an ordered list of blocks, and links
     attach a block to a place in the book. No similarity job runs for these:
     every link comes from generation or from the student, so the section-level
     matcher has nothing to add.
"""

from __future__ import annotations

import hashlib
import re
import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.db import utcnow
from app.models.note_block import BlockKind, BlockOrigin, NoteBlock
from app.models.note_link import LinkOrigin, LinkStatus, NoteLink
from app.models.note_session import NoteSession, NoteSessionStatus, NoteSource


# ── Pydantic response schemas ─────────────────────────────────


class NoteSessionResponse(BaseModel):
    """One note session, as returned by both create and list.

    ``job_id`` is only known on the reply to a create request, where it carries
    the queued similarity job. A session read back later has no live job, so the
    field is optional rather than invented -- requiring it is what made
    ``GET /notes`` fail validation on every stored row.

    ``section_ids`` carries the sections this note cites, so a client can work
    out "notes on this section" without a second request -- on this link, that
    request is the whole cost.
    """

    id: uuid.UUID
    book_id: uuid.UUID
    title: Optional[str] = None
    source: NoteSource
    status: NoteSessionStatus
    matched_section_count: Optional[int] = None
    job_id: Optional[str] = None
    created_at: datetime
    section_ids: list[uuid.UUID] = []

    model_config = ConfigDict(from_attributes=True)

class NoteSessionListResponse(BaseModel):
    """List of note sessions returned to the client."""
    sessions: list[NoteSessionResponse]
    total: int


# ── Service functions ──────────────────────────────────────────


async def create_note_session(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    book_id: uuid.UUID,
    raw_text: str,
    source: NoteSource,
    title: Optional[str] = None,
) -> NoteSessionResponse:
    """Create a note session and enqueue a background similarity job.

    Args:
        db: Async SQLAlchemy session.
        user_id: Authenticated user.
        book_id: Target book.
        raw_text: The pasted/typed note text.
        source: ``NoteSource.PASTED`` or ``NoteSource.AI_GENERATED``.
        title: Optional human-readable title.

    Returns:
        ``NoteSessionResponse`` with the session record and the
        Dramatiq job ID for status polling.
    """
    session = NoteSession(
        user_id=user_id,
        book_id=book_id,
        raw_text=raw_text,
        source=source,
        title=title,
        status=NoteSessionStatus.PENDING,
    )
    db.add(session)
    await db.flush()  # get the session.id

    # Enqueue background similarity job
    # Lazy import avoids pulling in Dramatiq broker at module load time.
    from app.workers.note_session import process_note_session  # noqa: C0301
    job = process_note_session.send(str(session.id))

    await db.commit()

    return NoteSessionResponse(
        id=session.id,
        book_id=session.book_id,
        title=session.title,
        source=session.source,
        status=session.status,
        matched_section_count=session.matched_section_count,
        job_id=job.message_id,
        created_at=session.created_at,
    )


async def _section_ids_by_note(    db: AsyncSession,
    note_ids: list[uuid.UUID],
) -> dict[uuid.UUID, list[uuid.UUID]]:
    """Which sections each note cites, for a whole page, in one query.

    Returned alongside the list so a client can show "notes on this section"
    without asking again: on this link, one round trip is the entire cost.
    """
    if not note_ids:
        return {}

    rows = await db.execute(
        select(NoteBlock.note_id, NoteLink.section_id)
        .join(NoteLink, NoteLink.block_id == NoteBlock.id)
        .where(
            NoteBlock.note_id.in_(note_ids),
            NoteLink.section_id.isnot(None),
            NoteLink.status == LinkStatus.ACCEPTED,
        )
        .distinct()
    )
    grouped: dict[uuid.UUID, list[uuid.UUID]] = {}
    for note_id, section_id in rows.all():
        grouped.setdefault(note_id, []).append(section_id)
    return grouped


def _session_responses(
    sessions: list[NoteSession],
    section_ids: dict[uuid.UUID, list[uuid.UUID]],
) -> list[NoteSessionResponse]:
    """Attach each note's cited section ids to its summary."""
    responses: list[NoteSessionResponse] = []
    for session in sessions:
        response = NoteSessionResponse.model_validate(session)
        response.section_ids = section_ids.get(session.id, [])
        responses.append(response)
    return responses


async def list_note_sessions(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    book_id: uuid.UUID,
    limit: int = 50,
    offset: int = 0,
) -> NoteSessionListResponse:
    """List note sessions for a user + book, most recent first."""
    result = await db.execute(
        select(NoteSession)
        .where(
            NoteSession.user_id == user_id,
            NoteSession.book_id == book_id,
        )
        .order_by(NoteSession.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    sessions = list(result.scalars().all())

    # A page shorter than the limit is proof there is nothing after it, so the
    # count query is unnecessary -- one fewer round trip on the common path,
    # and a round trip to this database costs about a second.
    if len(sessions) < limit:
        total = offset + len(sessions)
    else:
        total = (
            await db.execute(
                select(func.count())
                .select_from(NoteSession)
                .where(
                    NoteSession.user_id == user_id,
                    NoteSession.book_id == book_id,
                )
            )
        ).scalar_one()

    section_ids = await _section_ids_by_note(db, [s.id for s in sessions])
    return NoteSessionListResponse(
        sessions=_session_responses(sessions, section_ids),
        total=total,
    )

async def list_notes_for_section(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    book_id: uuid.UUID,
    section_id: uuid.UUID,
    limit: int = 20,
) -> NoteSessionListResponse:
    """Notes that cite this section — "your notes on this section".

    Only accepted links count: a dismissed link is not a citation the student
    kept. One note appears once however many of its blocks cite the section,
    which is what ``distinct()`` is for.
    """
    citation_filter = (
        NoteSession.user_id == user_id,
        NoteSession.book_id == book_id,
        NoteLink.section_id == section_id,
        NoteLink.status == LinkStatus.ACCEPTED,
    )

    def citing_notes(columns):
        return (
            select(columns)
            .join(NoteBlock, NoteBlock.note_id == NoteSession.id)
            .join(NoteLink, NoteLink.block_id == NoteBlock.id)
            .where(*citation_filter)
            .distinct()
        )

    sessions = list(
        (
            await db.execute(
                citing_notes(NoteSession)
                .order_by(NoteSession.created_at.desc())
                .limit(limit)
            )
        ).scalars().all()
    )

    if len(sessions) < limit:
        total = len(sessions)
    else:
        total = (
            await db.execute(
                select(func.count(func.distinct(NoteSession.id)))
                .select_from(NoteSession)
                .join(NoteBlock, NoteBlock.note_id == NoteSession.id)
                .join(NoteLink, NoteLink.block_id == NoteBlock.id)
                .where(*citation_filter)
            )
        ).scalar_one()

    # Every note in this list cites the section by construction.
    return NoteSessionListResponse(
        sessions=_session_responses(
            sessions, {session.id: [section_id] for session in sessions}
        ),
        total=total,
    )

# ── Note documents: blocks and their links ────────────────────

# Whitespace is collapsed before hashing so a reflowed paragraph is not
# mistaken for new text. Case is left alone: changing case is a real edit.
_WHITESPACE_RE = re.compile(r"\s+")


class NoteLinkDraft(BaseModel):
    """A link to store against a block.

    ``excerpt_hash`` is deliberately absent: the server derives it from the
    excerpt, so a client can never store a hash that does not match the text.
    """

    section_id: Optional[uuid.UUID] = None
    anchor_heading_path: str
    page_start: int
    page_end: int
    excerpt: str
    origin: LinkOrigin
    status: LinkStatus = LinkStatus.ACCEPTED


class NoteBlockDraft(BaseModel):
    """One block as the client (or the generator) submits it.

    ``id`` is present for a block that already exists, which is how autosave
    keeps its links: the block row is updated in place rather than replaced.
    Position is not accepted from the client -- the list index is the order.
    """

    id: Optional[uuid.UUID] = None
    kind: BlockKind
    text: str
    origin: BlockOrigin = BlockOrigin.TYPED
    links: list[NoteLinkDraft] = []


class NoteLinkResponse(BaseModel):
    """One stored link, as the note view renders it as a chip."""

    id: uuid.UUID
    section_id: Optional[uuid.UUID] = None
    anchor_heading_path: str
    page_start: int
    page_end: int
    excerpt: str
    status: LinkStatus
    origin: LinkOrigin


class NoteBlockResponse(BaseModel):
    """One stored block with the links attached to it."""

    id: uuid.UUID
    position: int
    kind: BlockKind
    text: str
    origin: BlockOrigin
    links: list[NoteLinkResponse] = []


class NoteDetailResponse(BaseModel):
    """A whole note: its header plus its blocks in order.

    ``raw_text`` is included for notes that predate blocks -- a session created
    by the paste flow has text but no block rows, and the view would otherwise
    call it empty.
    """

    id: uuid.UUID
    book_id: uuid.UUID
    title: Optional[str] = None
    source: NoteSource
    status: NoteSessionStatus
    matched_section_count: Optional[int] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    raw_text: str = ""
    blocks: list[NoteBlockResponse] = []


def _normalise(text: str) -> str:
    """Collapse runs of whitespace so reflowing a block does not count as a change."""
    return _WHITESPACE_RE.sub(" ", text).strip()


def _hash(text: str) -> str:
    """sha256 of the normalised text, as stored in ``content_hash``/``excerpt_hash``."""
    return hashlib.sha256(_normalise(text).encode("utf-8")).hexdigest()


def _link_response(link: NoteLink) -> NoteLinkResponse:
    return NoteLinkResponse(
        id=link.id,
        section_id=link.section_id,
        anchor_heading_path=link.anchor_heading_path,
        page_start=link.page_start,
        page_end=link.page_end,
        excerpt=link.excerpt,
        status=link.status,
        origin=link.origin,
    )


def _block_response(block: NoteBlock) -> NoteBlockResponse:
    return NoteBlockResponse(
        id=block.id,
        position=block.position,
        kind=block.kind,
        text=block.text,
        origin=block.origin,
        links=[_link_response(link) for link in block.links],
    )


def _detail_response(note: NoteSession) -> NoteDetailResponse:
    """Build the response from loaded attributes only.

    Written out rather than ``model_validate`` on purpose: a lazy relationship
    on an async session raises, so the caller must have loaded ``blocks``.
    """
    return NoteDetailResponse(
        id=note.id,
        book_id=note.book_id,
        title=note.title,
        source=note.source,
        status=note.status,
        matched_section_count=note.matched_section_count,
        created_at=note.created_at,
        updated_at=note.updated_at,
        raw_text=note.raw_text,
        blocks=[_block_response(block) for block in note.blocks],
    )


def _insert_links(
    db: AsyncSession,
    block_id: uuid.UUID,
    drafts: list[NoteLinkDraft],
) -> None:
    """Queue the links for one block, deriving each excerpt hash server-side."""
    for draft in drafts:
        db.add(
            NoteLink(
                block_id=block_id,
                section_id=draft.section_id,
                anchor_heading_path=draft.anchor_heading_path,
                page_start=draft.page_start,
                page_end=draft.page_end,
                excerpt=draft.excerpt,
                excerpt_hash=_hash(draft.excerpt),
                origin=draft.origin,
                status=draft.status,
            )
        )


def _apply_edit(block: NoteBlock, position: int, draft: NoteBlockDraft) -> None:
    """Update a block in place, leaving it untouched when nothing changed.

    Links are not touched: autosave edits text, and a link survives an edit
    because it is attached to the block, not to a character offset.

    ``origin`` is not touched either. It records where the text came from, which
    an edit does not change -- otherwise every autosave would rewrite an
    AI-generated block as typed.
    """
    if block.position != position:
        block.position = position
    if block.kind != draft.kind:
        block.kind = draft.kind
    content_hash = _hash(draft.text)
    if block.content_hash != content_hash:
        block.text = draft.text
        block.content_hash = content_hash


async def _linked_section_count(db: AsyncSession, note_id: uuid.UUID) -> int:
    """Distinct sections this note cites, counting accepted links only.

    This is what ``matched_section_count`` means for a block note, so the
    sessions list stays meaningful now that no similarity pass runs.
    """
    rows = await db.execute(
        select(NoteLink.section_id)
        .join(NoteBlock, NoteLink.block_id == NoteBlock.id)
        .where(
            NoteBlock.note_id == note_id,
            NoteLink.section_id.isnot(None),
            NoteLink.status == LinkStatus.ACCEPTED,
        )
    )
    return len({row[0] for row in rows.all()})


async def create_note_with_blocks(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    book_id: uuid.UUID,
    blocks: list[NoteBlockDraft],
    source: NoteSource,
    title: Optional[str] = None,
) -> NoteDetailResponse:
    """Create a note document from validated blocks.

    No similarity job is enqueued -- see the module docstring. ``raw_text`` is
    still filled with the assembled text so the legacy column, the sessions
    list and the block view never disagree about what the note says.
    """
    note = NoteSession(
        user_id=user_id,
        book_id=book_id,
        title=title,
        source=source,
        raw_text="\n\n".join(block.text for block in blocks),
        status=NoteSessionStatus.COMPLETED,
    )
    db.add(note)
    await db.flush()  # assigns note.id

    created: list[tuple[NoteBlock, NoteBlockDraft]] = []
    for position, draft in enumerate(blocks):
        block = NoteBlock(
            note_id=note.id,
            position=position,
            kind=draft.kind,
            text=draft.text,
            content_hash=_hash(draft.text),
            origin=draft.origin,
        )
        db.add(block)
        created.append((block, draft))

    await db.flush()  # assigns every block.id
    for block, draft in created:
        _insert_links(db, block.id, draft.links)

    await db.flush()
    note.matched_section_count = await _linked_section_count(db, note.id)
    await db.commit()

    detail = await get_note_detail(db, user_id=user_id, note_id=note.id)
    assert detail is not None, "a note created in this transaction must be readable"
    return detail


async def replace_note_blocks(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    note_id: uuid.UUID,
    blocks: list[NoteBlockDraft],
) -> NoteDetailResponse:
    """Save the editor's full block list, preserving links on blocks that survive.

    Blocks are matched by ``id``: an existing block is updated in place so its
    links stay attached, a block without an id (or with an id that belongs to
    another note) is inserted, and any stored block missing from the payload is
    deleted. An unknown id is inserted rather than rejected -- autosave must not
    fail because a client raced a deletion.

    Raises ``ValueError`` when the note does not exist or belongs to someone
    else; the router turns that into a 404 rather than leaking existence.
    """
    result = await db.execute(
        select(NoteSession)
        .where(NoteSession.id == note_id, NoteSession.user_id == user_id)
        .options(selectinload(NoteSession.blocks))
    )
    note = result.scalar_one_or_none()
    if note is None:
        raise ValueError(f"Note {note_id} not found")

    existing = {block.id: block for block in note.blocks}
    kept: set[uuid.UUID] = set()
    fresh: list[tuple[NoteBlock, NoteBlockDraft]] = []

    for position, draft in enumerate(blocks):
        # A payload naming the same block twice is a client bug, and honouring
        # both is the worst response: the second update overwrites the first
        # one's text, so a split paragraph would silently lose half its words.
        # The later occurrence is stored as a new block instead -- no text can
        # disappear because of it.
        block = (
            existing.get(draft.id)
            if draft.id is not None and draft.id not in kept
            else None
        )
        if block is not None:
            kept.add(block.id)
            _apply_edit(block, position, draft)
        else:
            new_block = NoteBlock(
                note_id=note.id,
                position=position,
                kind=draft.kind,
                text=draft.text,
                content_hash=_hash(draft.text),
                origin=draft.origin,
            )
            db.add(new_block)
            fresh.append((new_block, draft))

    for block in note.blocks:
        if block.id not in kept:
            await db.delete(block)

    await db.flush()  # assigns ids for the inserted blocks
    for block, draft in fresh:
        _insert_links(db, block.id, draft.links)

    note.raw_text = "\n\n".join(block.text for block in blocks)
    await db.flush()
    note.matched_section_count = await _linked_section_count(db, note.id)
    await db.commit()

    detail = await get_note_detail(db, user_id=user_id, note_id=note.id)
    assert detail is not None, "a note saved in this transaction must be readable"
    return detail


async def get_note_detail(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    note_id: uuid.UUID,
) -> Optional[NoteDetailResponse]:
    """One note with its blocks and links, or ``None`` if not the caller's.

    ``populate_existing`` matters: this is also called immediately after a
    write in the same session, and without it the identity map hands back the
    pre-write collection of blocks instead of re-reading them.
    """
    result = await db.execute(
        select(NoteSession)
        .where(NoteSession.id == note_id, NoteSession.user_id == user_id)
        .options(selectinload(NoteSession.blocks).selectinload(NoteBlock.links))
        .execution_options(populate_existing=True)
    )
    note = result.scalar_one_or_none()
    if note is None:
        return None
    return _detail_response(note)


# ── Batched upsert (local-first write-behind) ─────────────────


class NoteBatchLink(BaseModel):
    """A link as the local store holds it: client id, no server-only fields."""

    id: uuid.UUID
    section_id: Optional[uuid.UUID] = None
    anchor_heading_path: str
    page_start: int
    page_end: int
    excerpt: str
    status: LinkStatus = LinkStatus.ACCEPTED
    origin: LinkOrigin


class NoteBatchBlock(BaseModel):
    """A block with a client-generated id, so the upsert is idempotent."""

    id: uuid.UUID
    kind: BlockKind
    text: str
    origin: BlockOrigin = BlockOrigin.TYPED
    links: list[NoteBatchLink] = []


class NoteBatchNote(BaseModel):
    """One note's full current state, as flushed by the client."""

    id: uuid.UUID
    book_id: uuid.UUID
    title: Optional[str] = None
    source: NoteSource
    blocks: list[NoteBatchBlock] = []


def _upsert_insert(db: AsyncSession, model):
    """A dialect ``INSERT`` that supports ``ON CONFLICT``.

    Postgres in production, SQLite in the test harness -- both expose
    ``on_conflict_do_update``. Chosen from the *session's* dialect, not the
    global engine, so tests actually exercise the SQLite path.
    """
    if db.get_bind().dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    else:
        from sqlalchemy.dialects.sqlite import insert
    return insert(model)


async def upsert_notes_batch(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    notes: list[NoteBatchNote],
    deleted: list[uuid.UUID] | None = None,
) -> list[tuple[uuid.UUID, datetime]]:
    """Upsert many notes' current state in one transaction.

    The client is the source of truth (last-writer-wins), so each note arrives as
    its full current block list. This collapses "one save per note" into a single
    round trip: one multi-row ``INSERT ... ON CONFLICT`` per table, then deletes
    for rows the client dropped. Client ids ARE the row ids, so a replay is
    idempotent and a retried outbox never duplicates.

    Returns ``(note_id, updated_at)`` for every note that was written.
    """
    deleted = deleted or []
    if not notes and not deleted:
        return []

    now = utcnow()

    # Delete owned notes first. Children are removed explicitly so this works
    # whether or not the database enforces ON DELETE CASCADE.
    if deleted:
        owned = await db.execute(
            select(NoteSession.id).where(
                NoteSession.id.in_(deleted), NoteSession.user_id == user_id
            )
        )
        doomed = [row[0] for row in owned.all()]
        if doomed:
            doomed_blocks = select(NoteBlock.id).where(NoteBlock.note_id.in_(doomed))
            await db.execute(
                delete(NoteLink).where(NoteLink.block_id.in_(doomed_blocks))
            )
            await db.execute(delete(NoteBlock).where(NoteBlock.note_id.in_(doomed)))
            await db.execute(
                delete(NoteSession).where(
                    NoteSession.id.in_(doomed), NoteSession.user_id == user_id
                )
            )

    if not notes:
        await db.commit()
        return []

    note_ids = [note.id for note in notes]

    # Ownership guard: a client must never overwrite another user's note.
    owner_rows = await db.execute(
        select(NoteSession.id, NoteSession.user_id).where(
            NoteSession.id.in_(note_ids)
        )
    )
    owners = {row[0]: row[1] for row in owner_rows.all()}
    allowed = [note for note in notes if owners.get(note.id) in (None, user_id)]
    if not allowed:
        await db.commit()
        return []

    # 1. Headers -- one multi-row upsert.
    session_rows = []
    for note in allowed:
        accepted_sections = {
            link.section_id
            for block in note.blocks
            for link in block.links
            if link.status == LinkStatus.ACCEPTED and link.section_id is not None
        }
        session_rows.append(
            {
                "id": note.id,
                "user_id": user_id,
                "book_id": note.book_id,
                "title": note.title,
                "source": note.source,
                "raw_text": "\n\n".join(block.text for block in note.blocks),
                "status": NoteSessionStatus.COMPLETED,
                "matched_section_count": len(accepted_sections),
                "created_at": now,
                "updated_at": now,
            }
        )
    note_ins = _upsert_insert(db, NoteSession).values(session_rows)
    await db.execute(
        note_ins.on_conflict_do_update(
            index_elements=[NoteSession.id],
            set_={
                "title": note_ins.excluded.title,
                "source": note_ins.excluded.source,
                "raw_text": note_ins.excluded.raw_text,
                "status": note_ins.excluded.status,
                "matched_section_count": note_ins.excluded.matched_section_count,
                "updated_at": note_ins.excluded.updated_at,
            },
        )
    )

    # 2. Blocks -- one multi-row upsert; skip unchanged text via content_hash.
    block_rows = []
    for note in allowed:
        for position, block in enumerate(note.blocks):
            block_rows.append(
                {
                    "id": block.id,
                    "note_id": note.id,
                    "position": position,
                    "kind": block.kind,
                    "text": block.text,
                    "content_hash": _hash(block.text),
                    "origin": block.origin,
                    "created_at": now,
                    "updated_at": now,
                }
            )
    if block_rows:
        block_ins = _upsert_insert(db, NoteBlock).values(block_rows)
        await db.execute(
            block_ins.on_conflict_do_update(
                index_elements=[NoteBlock.id],
                set_={
                    "position": block_ins.excluded.position,
                    "kind": block_ins.excluded.kind,
                    "text": block_ins.excluded.text,
                    "content_hash": block_ins.excluded.content_hash,
                    "updated_at": block_ins.excluded.updated_at,
                },
                where=NoteBlock.content_hash != block_ins.excluded.content_hash,
            )
        )

    # 3. Links -- one multi-row upsert (excerpt_hash derived server-side).
    link_rows = []
    for note in allowed:
        for block in note.blocks:
            for link in block.links:
                link_rows.append(
                    {
                        "id": link.id,
                        "block_id": block.id,
                        "section_id": link.section_id,
                        "anchor_heading_path": link.anchor_heading_path,
                        "page_start": link.page_start,
                        "page_end": link.page_end,
                        "excerpt": link.excerpt,
                        "excerpt_hash": _hash(link.excerpt),
                        "origin": link.origin,
                        "status": link.status,
                        "created_at": now,
                        "updated_at": now,
                    }
                )
    if link_rows:
        link_ins = _upsert_insert(db, NoteLink).values(link_rows)
        await db.execute(
            link_ins.on_conflict_do_update(
                index_elements=[NoteLink.id],
                set_={
                    "section_id": link_ins.excluded.section_id,
                    "anchor_heading_path": link_ins.excluded.anchor_heading_path,
                    "page_start": link_ins.excluded.page_start,
                    "page_end": link_ins.excluded.page_end,
                    "excerpt": link_ins.excluded.excerpt,
                    "excerpt_hash": link_ins.excluded.excerpt_hash,
                    "origin": link_ins.excluded.origin,
                    "status": link_ins.excluded.status,
                    "updated_at": link_ins.excluded.updated_at,
                },
            )
        )

    # 4. Drop blocks the client removed (their links cascade away).
    for note in allowed:
        keep_blocks = [block.id for block in note.blocks]
        delete_blocks = delete(NoteBlock).where(NoteBlock.note_id == note.id)
        if keep_blocks:
            delete_blocks = delete_blocks.where(NoteBlock.id.notin_(keep_blocks))
        await db.execute(delete_blocks)

    # 5. Drop links the client removed (on surviving blocks).
    for note in allowed:
        keep_links = [link.id for block in note.blocks for link in block.links]
        block_ids = select(NoteBlock.id).where(NoteBlock.note_id == note.id)
        delete_links = delete(NoteLink).where(NoteLink.block_id.in_(block_ids))
        if keep_links:
            delete_links = delete_links.where(NoteLink.id.notin_(keep_links))
        await db.execute(delete_links)

    await db.commit()
    return [(note.id, now) for note in allowed]
