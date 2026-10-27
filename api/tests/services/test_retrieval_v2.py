"""Retrieval v2 unit tests (plan unit U8).

These cover the pure decision helpers. The ranking itself needs a database and a
real embedder, so it is measured by the eval harness rather than here.
"""

from __future__ import annotations

import uuid

import pytest

from app.core.config import settings
from app.models.section import Section
from app.services.retrieval import (
    _candidate_limit,
    _dedup_by_section,
    _is_connective_stub,
)


def _section(
    *,
    connective: bool = True,
    metadata: dict | None = None,
    heading: str = "Some Section",
) -> Section:
    return Section(
        heading=heading,
        is_connective=connective,
        section_metadata=metadata or {},
        chapter_index=0,
        section_index=0,
        level=1,
        page_start=1,
        page_end=1,
        word_count=100,
    )


def _chunk(section_id: uuid.UUID, chunk_index: int = 0):
    class _C:
        pass

    chunk = _C()
    chunk.section_id = section_id
    chunk.chunk_index = chunk_index
    return chunk


# --------------------------------------------------------------------------
# Connective stubs
# --------------------------------------------------------------------------


def test_a_short_leaf_section_with_no_content_is_a_stub() -> None:
    assert _is_connective_stub(_section(), has_children=False) is True


def test_a_container_section_is_never_a_stub() -> None:
    """Its text lives in child subsections, so excluding it loses real content."""
    assert _is_connective_stub(_section(), has_children=True) is False


def test_a_connective_section_with_definitions_is_not_a_stub() -> None:
    section = _section(metadata={"definitions": ["B-tree: a balanced tree"]})

    assert _is_connective_stub(section, has_children=False) is False


@pytest.mark.parametrize("field", ["equations", "examples"])
def test_other_content_fields_also_disqualify_a_stub(field: str) -> None:
    section = _section(metadata={field: ["something"]})

    assert _is_connective_stub(section, has_children=False) is False


def test_a_non_connective_section_is_never_a_stub() -> None:
    assert _is_connective_stub(_section(connective=False), has_children=False) is False


# --------------------------------------------------------------------------
# Dedup
# --------------------------------------------------------------------------


def test_dedup_keeps_only_the_first_chunk_per_section() -> None:
    a, b = uuid.uuid4(), uuid.uuid4()
    hits = [
        (_chunk(a), 0.10),
        (_chunk(a), 0.12),
        (_chunk(b), 0.15),
        (_chunk(a), 0.20),
    ]

    kept = _dedup_by_section(hits)

    assert [distance for _chunk_, distance in kept] == [0.10, 0.15]


def test_dedup_preserves_distance_order() -> None:
    a, b, c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    hits = [(_chunk(a), 0.1), (_chunk(b), 0.2), (_chunk(c), 0.3)]

    kept = _dedup_by_section(hits)

    assert [distance for _chunk_, distance in kept] == [0.1, 0.2, 0.3]


def test_dedup_of_an_empty_list_is_empty() -> None:
    assert _dedup_by_section([]) == []


# --------------------------------------------------------------------------
# Over-fetching
# --------------------------------------------------------------------------


def test_overfetch_is_disabled_when_nothing_filters(monkeypatch) -> None:
    monkeypatch.setattr(settings, "retrieval_dedup_sections", False)
    monkeypatch.setattr(settings, "retrieval_exclude_connective", False)

    assert _candidate_limit(5) == 5


def test_overfetch_applies_when_dedup_is_on(monkeypatch) -> None:
    monkeypatch.setattr(settings, "retrieval_dedup_sections", True)
    monkeypatch.setattr(settings, "retrieval_exclude_connective", False)
    monkeypatch.setattr(settings, "retrieval_overfetch", 3)

    assert _candidate_limit(5) == 15


def test_overfetch_never_multiplies_by_zero(monkeypatch) -> None:
    monkeypatch.setattr(settings, "retrieval_dedup_sections", True)
    monkeypatch.setattr(settings, "retrieval_overfetch", 0)

    assert _candidate_limit(5) == 5
