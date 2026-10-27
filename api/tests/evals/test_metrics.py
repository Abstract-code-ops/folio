"""Tests for the eval harness (plan unit U1).

These run entirely on fixtures: no database, no Ollama, no LLM. The metric
maths and the golden-set loader are pure, so this is the cheap gate that
proves the harness works before anyone runs it against real books.
"""

from __future__ import annotations

import json

import pytest

from evals.metrics import (
    RetrievedChunk,
    aggregate,
    aggregate_by_type,
    load_questions,
    normalise_heading,
    page_bounds,
    score_question,
)


def _chunk(
    *,
    chunk_id: str = "c1",
    section_id: str = "s1",
    heading: str = "Section One",
    index: int = 0,
    words: int = 100,
    page_start: int | None = None,
    page_end: int | None = None,
    distance: float | None = None,
) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id,
        section_id=section_id,
        section_heading=heading,
        chunk_index=index,
        word_count=words,
        page_start=page_start,
        page_end=page_end,
        distance=distance,
    )


def _question(**overrides):
    base = {
        "id": "q1",
        "book_id": "book-1",
        "type": "definition",
        "question": "What is a thing?",
        "history": [],
        "gold_sections": ["Section One"],
        "gold_pages": [10, 12],
        "verified": True,
    }
    base.update(overrides)
    return base


# --------------------------------------------------------------------------
# Normalisation and page bounds
# --------------------------------------------------------------------------


def test_normalise_heading_unifies_dashes_case_and_whitespace():
    assert normalise_heading("Variations on a Scheme \u2014 Lazy Evaluation") == (
        normalise_heading("variations on a  scheme - lazy evaluation")
    )


def test_normalise_heading_keeps_distinct_headings_distinct():
    assert normalise_heading("B-trees") != normalise_heading("SSTables and LSM-trees")


@pytest.mark.parametrize(
    ("gold", "expected"),
    [
        ([], None),
        ([30], (30, 30)),
        ([99, 103], (99, 103)),
        ([103, 99], (99, 103)),
        ([5, 6, 7], (5, 7)),
    ],
)
def test_page_bounds(gold, expected):
    assert page_bounds(gold) == expected


# --------------------------------------------------------------------------
# Question scoring
# --------------------------------------------------------------------------


def test_hit_at_rank_one_gives_full_reciprocal_rank():
    score = score_question(_question(), [_chunk()], context_words=500)
    assert score.section_hit is True
    assert score.reciprocal_rank == 1.0


def test_hit_at_rank_three_gives_one_third():
    retrieved = [
        _chunk(chunk_id="c1", section_id="s1", heading="Other A", distance=0.4),
        _chunk(chunk_id="c2", section_id="s2", heading="Other B", distance=0.3),
        _chunk(chunk_id="c3", section_id="s3", heading="Section One", distance=0.2),
    ]
    score = score_question(_question(), retrieved, context_words=500)
    assert score.section_hit is True
    assert score.reciprocal_rank == pytest.approx(1 / 3)


def test_miss_gives_zero_reciprocal_rank():
    score = score_question(
        _question(), [_chunk(heading="Something Else")], context_words=500
    )
    assert score.section_hit is False
    assert score.reciprocal_rank == 0.0


def test_matching_ignores_heading_punctuation_differences():
    score = score_question(
        _question(gold_sections=["Scheme \u2014 Lazy"]),
        [_chunk(heading="Scheme - Lazy")],
        context_words=1,
    )
    assert score.section_hit is True


def test_distinct_sections_counts_unique_sections_not_chunks():
    retrieved = [
        _chunk(chunk_id="c1", section_id="s1"),
        _chunk(chunk_id="c2", section_id="s1"),
        _chunk(chunk_id="c3", section_id="s2"),
    ]
    score = score_question(_question(), retrieved, context_words=300)
    assert score.distinct_sections == 2


def test_best_distance_is_the_smallest_of_the_retrieved_distances():
    retrieved = [
        _chunk(chunk_id="c1", distance=0.51),
        _chunk(chunk_id="c2", distance=0.22),
        _chunk(chunk_id="c3", distance=0.38),
    ]
    score = score_question(_question(), retrieved, context_words=300)
    assert score.best_distance == pytest.approx(0.22)


# --------------------------------------------------------------------------
# page_hit@5 is unavailable until chunks carry page ranges
# --------------------------------------------------------------------------


def test_page_hit_is_none_without_chunk_pages():
    score = score_question(_question(), [_chunk(heading="Section One")], context_words=1)
    assert score.page_hit is None


def test_page_hit_true_when_a_chunk_range_intersects_gold_pages():
    retrieved = [_chunk(heading="Other", page_start=11, page_end=14)]
    score = score_question(_question(gold_pages=[10, 12]), retrieved, context_words=1)
    assert score.page_hit is True


def test_page_hit_false_when_no_range_intersects():
    retrieved = [_chunk(heading="Other", page_start=40, page_end=44)]
    score = score_question(_question(gold_pages=[10, 12]), retrieved, context_words=1)
    assert score.page_hit is False


def test_page_hit_is_none_when_the_question_has_no_gold_pages():
    retrieved = [_chunk(heading="Other", page_start=40, page_end=44)]
    score = score_question(
        _question(gold_sections=[], gold_pages=[]), retrieved, context_words=1
    )
    assert score.page_hit is None


# --------------------------------------------------------------------------
# Aggregation
# --------------------------------------------------------------------------


def test_aggregate_reports_rates_and_averages():
    scores = [
        score_question(_question(id="a"), [_chunk()], context_words=100),
        score_question(
            _question(id="b"), [_chunk(heading="Elsewhere")], context_words=300
        ),
    ]
    agg = aggregate(scores)
    assert agg.n == 2
    assert agg.section_hit_at_5 == pytest.approx(0.5)
    assert agg.mrr == pytest.approx(0.5)
    assert agg.avg_context_words == pytest.approx(200.0)
    assert agg.page_hit_at_5 is None
    assert agg.page_hit_scored == 0


def test_aggregate_of_nothing_is_zeroed_not_an_error():
    agg = aggregate([])
    assert agg.n == 0
    assert agg.section_hit_at_5 == 0.0
    assert agg.page_hit_at_5 is None
    assert agg.in_scope_best_distance is None


def test_in_scope_slice_excludes_out_of_scope_questions():
    scores = [
        score_question(_question(id="a", type="definition"), [_chunk()], 100),
        score_question(
            _question(
                id="b",
                type="out_of_scope",
                gold_sections=[],
                gold_pages=[],
            ),
            [_chunk(distance=0.55)],
            900,
        ),
    ]
    by_type = aggregate_by_type(scores)
    assert by_type["in_scope"].n == 1
    assert by_type["in_scope"].section_hit_at_5 == pytest.approx(1.0)
    assert by_type["out_of_scope"].section_hit_at_5 == pytest.approx(0.0)
    assert by_type["all"].n == 2


def test_distance_distributions_are_split_by_scope():
    scores = [
        score_question(
            _question(id="a", type="definition"),
            [_chunk(distance=0.2)],
            100,
        ),
        score_question(
            _question(
                id="b", type="out_of_scope", gold_sections=[], gold_pages=[]
            ),
            [_chunk(distance=0.6)],
            100,
        ),
    ]
    agg = aggregate(scores)
    assert agg.in_scope_best_distance is not None
    assert agg.out_of_scope_best_distance is not None
    assert agg.in_scope_best_distance["median"] == pytest.approx(0.2)
    assert agg.out_of_scope_best_distance["median"] == pytest.approx(0.6)


# --------------------------------------------------------------------------
# Golden-set loading
# --------------------------------------------------------------------------


def _write_jsonl(path, records):
    path.write_text(
        "\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8"
    )
    return path


def test_verified_only_is_the_default_filter(tmp_path):
    path = _write_jsonl(
        tmp_path / "set.jsonl",
        [
            _question(id="verified-q", verified=True),
            _question(id="draft-q", verified=False),
        ],
    )
    questions, warnings = load_questions([path])
    assert [q["id"] for q in questions] == ["verified-q"]
    assert warnings == []


def test_include_unverified_returns_both(tmp_path):
    path = _write_jsonl(
        tmp_path / "set.jsonl",
        [
            _question(id="verified-q", verified=True),
            _question(id="draft-q", verified=False),
        ],
    )
    questions, warnings = load_questions([path], verified_only=False)
    assert [q["id"] for q in questions] == ["verified-q", "draft-q"]
    assert warnings == []


def test_loader_warns_on_malformed_and_unknown_records(tmp_path):
    path = tmp_path / "set.jsonl"
    path.write_text(
        "\n".join(
            [
                '{"id": "ok", "book_id": "b", "type": "definition",',
                json.dumps(_question(id="bad-type", type="vibes")),
                json.dumps(_question(id="no-gold", gold_sections=[])),
                json.dumps(_question(id="kept")),
                json.dumps(_question(id="kept")),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    questions, warnings = load_questions([path], verified_only=False)

    assert [q["id"] for q in questions] == ["kept"]
    joined = "\n".join(warnings)
    assert "malformed JSON" in joined
    assert "unknown type" in joined
    assert "no gold_sections" in joined
    assert "duplicate id" in joined


def test_out_of_scope_questions_may_have_no_gold_sections(tmp_path):
    path = _write_jsonl(
        tmp_path / "set.jsonl",
        [
            _question(
                id="oos",
                type="out_of_scope",
                gold_sections=[],
                gold_pages=[],
            )
        ],
    )
    questions, warnings = load_questions([path], verified_only=False)
    assert [q["id"] for q in questions] == ["oos"]
    assert warnings == []


def test_blank_lines_are_skipped_silently(tmp_path):
    path = tmp_path / "set.jsonl"
    path.write_text(
        "\n" + json.dumps(_question(id="only")) + "\n\n", encoding="utf-8"
    )
    questions, warnings = load_questions([path], verified_only=False)
    assert [q["id"] for q in questions] == ["only"]
    assert warnings == []
