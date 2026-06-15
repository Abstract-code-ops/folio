"""Cosine similarity pass for note session matching.

Takes an embedded note text and compares it against section embeddings
using Python-side cosine distance. The core matching function is a pure
operation on plain data — callers fetch section embeddings themselves
and pass them in.

This design keeps the module stateless (no DB imports), testable on
any backend, and callable from both async FastAPI code and sync
Dramatiq workers without adaptation.

A future optimisation can delegate the distance computation to
pgvector's ``<=>`` operator for large books.
"""

from __future__ import annotations

import math
import uuid

# Default minimum cosine similarity for a note-to-section match.
# Tune via ``NOTES_SESSION_SIMILARITY_THRESHOLD`` env var if added to config.
DEFAULT_SIMILARITY_THRESHOLD: float = 0.75


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two equal-length vectors.

    Returns a value in [-1, 1] where 1 = identical direction.
    If either vector is all zeros, returns 0.
    """
    if not a or not b or len(a) != len(b):
        return 0.0

    dot = sum(ax * bx for ax, bx in zip(a, b))
    norm_a = math.sqrt(sum(ax * ax for ax in a))
    norm_b = math.sqrt(sum(bx * bx for bx in b))

    if norm_a == 0 or norm_b == 0:
        return 0.0

    return dot / (norm_a * norm_b)


def find_matching_sections(
    section_embeddings: list[tuple[uuid.UUID, list[float]]],
    query_embedding: list[float],
    *,
    threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
) -> list[tuple[uuid.UUID, float]]:
    """Return sections whose embeddings exceed the similarity threshold.

    Args:
        section_embeddings: List of ``(section_id, embedding_vector)``
            tuples for the target book. Only sections with embeddings
            should be included.
        query_embedding: Embedded note text vector.
        threshold: Minimum cosine similarity (default 0.75).

    Returns:
        List of ``(section_id, similarity_score)`` tuples, sorted by
        descending similarity.
    """
    matches: list[tuple[uuid.UUID, float]] = []
    for section_id, embedding in section_embeddings:
        if not embedding:
            continue
        score = cosine_similarity(query_embedding, embedding)
        if score >= threshold:
            matches.append((section_id, score))

    matches.sort(key=lambda x: x[1], reverse=True)
    return matches
