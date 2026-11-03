"""Retrieval over a book's chunks.

Lifted out of the Q&A service: notes need the same search, and one service
importing another is a boundary worth avoiding. Everything here is a pure
function over an explicit session -- no router, no service imports.

Retrieval v2 (plan unit U8) is what these functions implement:

- the nomic ``search_query:`` prefix behind ``embed_prefixes_enabled``, with an
  ``embed_version`` restriction so documents and queries never sit in different
  embedding spaces;
- the real cosine distance returned with every hit;
- an optional ``retrieval_max_distance`` cut-off, disabled by default;
- optional dedup by section, and optional exclusion of connective stubs.

Every toggle defaults to the behaviour that was measured on the eval.
"""

from __future__ import annotations

import os
import time
import uuid
from collections import OrderedDict
from typing import Optional

from llama_index.embeddings.ollama import OllamaEmbedding
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased, joinedload

from app.core.config import settings
from app.models.chunk import Chunk
from app.models.section import Section
from app.pipeline.embed_inputs import EMBED_VERSION, query_embed_text
# (768-dim, matching the pgvector column).
_embedder = OllamaEmbedding(
    model_name="nomic-embed-text",
    base_url=os.environ.get("OLLAMA_API_BASE", "http://localhost:11434"),
)

# A retrieved chunk paired with its cosine distance. Lower distance = closer.
Hit = tuple[Chunk, float]

# Small LRU of query embeddings. Repeated or refined queries reuse the vector
# instead of round-tripping to Ollama (CPU-bound, ~0.1-0.5s per call).
_EMBED_CACHE: "OrderedDict[str, list[float]]" = OrderedDict()
_EMBED_CACHE_MAX = 256


async def _embed_query(text: str) -> list[float]:
    cached = _EMBED_CACHE.get(text)
    if cached is not None:
        _EMBED_CACHE.move_to_end(text)
        return cached
    vector = await _embedder.aget_text_embedding(text)
    _EMBED_CACHE[text] = vector
    if len(_EMBED_CACHE) > _EMBED_CACHE_MAX:
        _EMBED_CACHE.popitem(last=False)
    return vector


def _candidate_limit(k: int) -> int:
    """Rows to fetch before filtering and dedup trim the list back to ``k``."""
    filtering = (
        settings.retrieval_dedup_sections or settings.retrieval_exclude_connective
    )
    if not filtering:
        return k
    return k * max(settings.retrieval_overfetch, 1)


def _is_connective_stub(section: Section, has_children: bool) -> bool:
    """True for a short section that owns no content of its own.

    Being short is not sufficient. After a heading split, a container section
    whose text lives in child subsections is also short -- three of the six
    flagged sections in the corpus are exactly that, and excluding them would
    drop the opening paragraph of a real section.
    """
    if not section.is_connective:
        return False
    if has_children:
        return False
    metadata = section.section_metadata or {}
    return not any(
        metadata.get(field) for field in ("definitions", "equations", "examples")
    )


def _dedup_by_section(hits: list[Hit]) -> list[Hit]:
    """Keep each section's best chunk. Hits arrive ordered by distance."""
    seen: set[uuid.UUID] = set()
    kept: list[Hit] = []
    for chunk, distance in hits:
        if chunk.section_id in seen:
            continue
        seen.add(chunk.section_id)
        kept.append((chunk, distance))
    return kept


async def retrieve_top_chunks(
    db: AsyncSession,
    book_id: uuid.UUID,
    question: str,
    k: int | None = None,
) -> list[Hit]:
    """Return up to ``k`` chunks with their cosine distance, closest first."""
    k = k or settings.retrieval_top_k
    query_embedding = await _embed_query(
        query_embed_text(question, prefixed=settings.embed_prefixes_enabled)
    )

    distance = Chunk.embedding.cosine_distance(query_embedding).label("distance")
    columns = [Chunk, distance]

    # The connective-stub filter needs a per-row "has children" check, which is a
    # correlated EXISTS subquery. Only compute it when the filter is on (off by
    # default), so the common query stays a plain vector scan.
    if settings.retrieval_exclude_connective:
        child = aliased(Section)
        has_children = (
            select(child.id).where(child.parent_section_id == Section.id).exists()
        )
        columns.append(has_children.label("has_children"))

    stmt = (
        select(*columns)
        .join(Section, Chunk.section_id == Section.id)
        .where(Section.book_id == book_id, Chunk.embedding.isnot(None))
        .options(joinedload(Chunk.section))
        .order_by(distance)
    )

    if settings.embed_prefixes_enabled:
        stmt = stmt.where(Chunk.embed_version >= EMBED_VERSION)
    if settings.retrieval_max_distance is not None:
        stmt = stmt.where(distance <= settings.retrieval_max_distance)

    stmt = stmt.limit(_candidate_limit(k))
    rows = (await db.execute(stmt)).all()

    hits: list[Hit] = []
    seen_ids: set[uuid.UUID] = set()
    for row in rows:
        chunk = row[0]
        chunk_distance = row[1]
        if chunk.id in seen_ids:
            continue
        seen_ids.add(chunk.id)
        if settings.retrieval_exclude_connective and _is_connective_stub(
            chunk.section, bool(row[2])
        ):
            continue
        hits.append((chunk, float(chunk_distance)))

    if settings.retrieval_dedup_sections:
        hits = _dedup_by_section(hits)

    return hits[:k]


_SECTION_INDEX_CACHE: dict[uuid.UUID, tuple[float, dict, list]] = {}
_SECTION_INDEX_TTL = 60.0


async def load_section_index(db: AsyncSession, book_id: uuid.UUID):
    """Section id -> (heading, parent_id), plus the same rows in document order.

    One query for the whole book, cached for a short window: expand_context asks
    for it on every search (and the agent can search more than once), so without
    the cache a turn reloads the whole book several times. Headings only change
    on re-ingest, so a 60s TTL is safe.
    """
    cached = _SECTION_INDEX_CACHE.get(book_id)
    if cached is not None and time.monotonic() - cached[0] < _SECTION_INDEX_TTL:
        return cached[1], cached[2]

    rows = (
        await db.execute(
            select(
                Section.id,
                Section.heading,
                Section.parent_section_id,
            )
            .where(Section.book_id == book_id)
            .order_by(Section.chapter_index, Section.section_index, Section.page_start)
        )
    ).all()
    index = {row[0]: (row[1], row[2]) for row in rows}
    if len(_SECTION_INDEX_CACHE) > 200:
        _SECTION_INDEX_CACHE.clear()
    _SECTION_INDEX_CACHE[book_id] = (time.monotonic(), index, rows)
    return index, rows


def breadcrumb(
    index: dict[uuid.UUID, tuple[str, Optional[uuid.UUID]]],
    section_id: uuid.UUID,
) -> str:
    """Ancestor headings then the section's own, joined with ' > '."""
    chain: list[str] = []
    cursor: Optional[uuid.UUID] = section_id
    guard = 0
    while cursor is not None and guard < 64:
        entry = index.get(cursor)
        if entry is None:
            break
        chain.append(entry[0])
        cursor = entry[1]
        guard += 1
    chain.reverse()
    return " > ".join(chain)
