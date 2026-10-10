"""Grounded Q&A business logic.

Retrieval uses pgvector cosine distance over the book's chunks, with
query embedding via LlamaIndex's Ollama embedding. Citations are built
from the retrieved chunks' real section/page metadata (not the LLM).
"""

from __future__ import annotations

import os
import uuid
from typing import Any

from llama_index.embeddings.ollama import OllamaEmbedding
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models.chunk import Chunk
from app.models.section import Section

TOP_K_CHUNKS = 5
EXCERPT_CHARS = 240

# Query embedding via LlamaIndex against local Ollama nomic-embed-text
# (768-dim, matching the pgvector column).
_embedder = OllamaEmbedding(
    model_name="nomic-embed-text",
    base_url=os.environ.get("OLLAMA_API_BASE", "http://localhost:11434"),
)


async def retrieve_top_chunks(
    db: AsyncSession,
    book_id: uuid.UUID,
    question: str,
    k: int = TOP_K_CHUNKS,
) -> list[Chunk]:
    """Return the top-k most similar chunks for a book via pgvector ``<=>``."""
    query_embedding = await _embedder.aget_text_embedding(question)

    result = await db.execute(
        select(Chunk)
        .join(Section, Chunk.section_id == Section.id)
        .where(
            Section.book_id == book_id,
            Chunk.embedding.isnot(None),
        )
        .options(joinedload(Chunk.section))
        .order_by(Chunk.embedding.cosine_distance(query_embedding))
        .limit(k)
    )
    return list(result.unique().scalars().all())


def build_citations(chunks: list[Chunk]) -> list[dict[str, Any]]:
    """Build source-citation events from the retrieved chunks' real metadata."""
    citations: list[dict[str, Any]] = []
    for chunk in chunks:
        section = chunk.section
        excerpt = chunk.content.strip()
        if len(excerpt) > EXCERPT_CHARS:
            excerpt = excerpt[:EXCERPT_CHARS].rstrip() + "..."
        citations.append({
            "type": "citation",
            "chunk_index": chunk.chunk_index,
            "section_heading": section.heading,
            "page_start": section.page_start,
            "page_end": section.page_end,
            "excerpt": excerpt,
        })
    return citations
