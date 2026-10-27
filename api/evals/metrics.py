"""Scoring and aggregation for the retrieval eval harness (plan unit U1).

Everything in this module is pure: no database, no network, no LLM, no
ORM imports. That keeps the metric maths unit-testable on fixtures, and it
guarantees the harness can be exercised in pytest without Ollama, Postgres,
or an embedding model.

The runner (`evals/runner.py`) does the I/O, converts ORM rows into
`RetrievedChunk`, and calls `score_question` / `aggregate` here.

Metric definitions (from the plan):

- ``section_hit@5``: at least one gold section is among the retrieved
  sections.
- ``page_hit@5``: a gold page falls inside a retrieved chunk's page range.
  ``None`` ("n/a") until chunks carry page ranges (U6 + U7).
- ``mrr``: reciprocal rank of the first retrieved chunk in a gold section,
  0.0 when no gold section is retrieved.
- ``distinct_sections@5``: how many different sections the five chunks cover.
- ``context_words``: word count of the assembled grounding context.
- ``best_distance``: smallest cosine distance among retrieved chunks, used
  to compare in-scope and out-of-scope distributions.
"""

from __future__ import annotations

import json
import re
import statistics
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence

EVAL_TYPES: tuple[str, ...] = (
    "definition",
    "ambiguous",
    "multi_section",
    "broad",
    "followup",
    "out_of_scope",
)

# Typographic characters that appear in real book headings ("Scheme - Lazy")
# but differ from what a question author types ("Scheme — Lazy").
_TRANSLATION = str.maketrans(
    {
        "\u2014": "-",  # em dash
        "\u2013": "-",  # en dash
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
    }
)


# --------------------------------------------------------------------------
# Data carried out of the runner
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class RetrievedChunk:
    """One retrieval result, decoupled from the ORM.

    ``page_start`` / ``page_end`` are ``None`` until chunks carry their own
    page ranges (U6 + U7), which is what makes ``page_hit@5`` unavailable
    today.
    """

    chunk_id: str
    section_id: str
    section_heading: str
    chunk_index: int
    word_count: int
    page_start: int | None = None
    page_end: int | None = None
    distance: float | None = None


@dataclass
class QuestionScore:
    """Per-question metrics."""

    question_id: str
    book_id: str
    type: str
    section_hit: bool
    page_hit: bool | None
    reciprocal_rank: float
    distinct_sections: int
    context_words: int
    best_distance: float | None
    returned_sections: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------
# Normalisation helpers
# --------------------------------------------------------------------------


def normalise_heading(value: str) -> str:
    """Normalise a section heading for comparison.

    Collapses internal whitespace, unifies typographic dashes and quotes,
    and case-folds, so ``"Scheme — Lazy Evaluation"`` matches
    ``"Variations on a Scheme - Lazy Evaluation"`` when the dash differs.
    """
    flattened = re.sub(r"\s+", " ", value.translate(_TRANSLATION)).strip()
    return flattened.casefold()


def page_bounds(gold_pages: Sequence[int]) -> tuple[int, int] | None:
    """Return inclusive ``(low, high)`` bounds for a gold page list.

    The golden set stores either a single page (``[30]``) or the inclusive
    bounds of the section's DB page range (``[99, 103]``). Both are handled
    by taking min/max, so a future revision that expands to every page keeps
    working unchanged.
    """
    if not gold_pages:
        return None
    return (min(gold_pages), max(gold_pages))


# --------------------------------------------------------------------------
# Scoring
# --------------------------------------------------------------------------


def score_question(
    question: dict[str, Any],
    retrieved: Sequence[RetrievedChunk],
    context_words: int,
) -> QuestionScore:
    """Score one question against the retrieved chunks.

    Args:
        question: One golden-set record (``id``, ``book_id``, ``type``,
            ``question``, ``gold_sections``, ``gold_pages``, ``verified``).
        retrieved: Retrieved chunks, best first.
        context_words: Word count of the grounding context built from them.
    """
    gold = {normalise_heading(name) for name in question.get("gold_sections", [])}
    bounds = page_bounds(question.get("gold_pages", []))

    reciprocal_rank = 0.0
    for rank, chunk in enumerate(retrieved, start=1):
        if normalise_heading(chunk.section_heading) in gold:
            reciprocal_rank = 1.0 / rank
            break

    section_hit = any(
        normalise_heading(chunk.section_heading) in gold for chunk in retrieved
    )

    # page_hit is only meaningful once chunks carry page ranges.
    page_hit: bool | None
    if bounds is None or not any(c.page_start is not None for c in retrieved):
        page_hit = None
    else:
        low, high = bounds
        page_hit = any(
            c.page_start is not None
            and c.page_end is not None
            and c.page_start <= high
            and c.page_end >= low
            for c in retrieved
        )

    distances = [c.distance for c in retrieved if c.distance is not None]

    return QuestionScore(
        question_id=str(question["id"]),
        book_id=str(question["book_id"]),
        type=str(question["type"]),
        section_hit=section_hit,
        page_hit=page_hit,
        reciprocal_rank=reciprocal_rank,
        distinct_sections=len({c.section_id for c in retrieved}),
        context_words=context_words,
        best_distance=min(distances) if distances else None,
        returned_sections=[c.section_heading for c in retrieved],
    )


# --------------------------------------------------------------------------
# Aggregation
# --------------------------------------------------------------------------


@dataclass
class Aggregate:
    """Aggregate metrics for one slice of the question set."""

    n: int
    section_hit_at_5: float
    page_hit_at_5: float | None
    page_hit_scored: int
    mrr: float
    distinct_sections_at_5: float
    avg_context_words: float
    in_scope_best_distance: dict[str, float] | None
    out_of_scope_best_distance: dict[str, float] | None


def _distribution(values: Iterable[float]) -> dict[str, float] | None:
    """min / median / max of a sample, or ``None`` when empty."""
    sample = [v for v in values if v is not None]
    if not sample:
        return None
    return {
        "n": len(sample),
        "min": min(sample),
        "median": statistics.median(sample),
        "max": max(sample),
    }


def aggregate(scores: Sequence[QuestionScore]) -> Aggregate:
    """Aggregate a slice of scores into the report metrics."""
    if not scores:
        return Aggregate(
            n=0,
            section_hit_at_5=0.0,
            page_hit_at_5=None,
            page_hit_scored=0,
            mrr=0.0,
            distinct_sections_at_5=0.0,
            avg_context_words=0.0,
            in_scope_best_distance=None,
            out_of_scope_best_distance=None,
        )

    page_scored = [s for s in scores if s.page_hit is not None]
    in_scope = [s for s in scores if s.type != "out_of_scope"]
    out_of_scope = [s for s in scores if s.type == "out_of_scope"]

    return Aggregate(
        n=len(scores),
        section_hit_at_5=sum(1 for s in scores if s.section_hit) / len(scores),
        page_hit_at_5=(
            sum(1 for s in page_scored if s.page_hit) / len(page_scored)
            if page_scored
            else None
        ),
        page_hit_scored=len(page_scored),
        mrr=sum(s.reciprocal_rank for s in scores) / len(scores),
        distinct_sections_at_5=sum(s.distinct_sections for s in scores) / len(scores),
        avg_context_words=sum(s.context_words for s in scores) / len(scores),
        in_scope_best_distance=_distribution(
            s.best_distance for s in in_scope if s.best_distance is not None
        ),
        out_of_scope_best_distance=_distribution(
            s.best_distance for s in out_of_scope if s.best_distance is not None
        ),
    )


def aggregate_by_type(
    scores: Sequence[QuestionScore],
) -> dict[str, Aggregate]:
    """Aggregate per question type, with ``in_scope`` first and ``all`` last.

    ``in_scope`` is the headline slice: out-of-scope questions have no gold
    section, so their ``section_hit`` is 0 by construction and including them
    in an average only dilutes the number.
    """
    result: dict[str, Aggregate] = {"in_scope": aggregate([
        s for s in scores if s.type != "out_of_scope"
    ])}
    for eval_type in EVAL_TYPES:
        subset = [s for s in scores if s.type == eval_type]
        if subset:
            result[eval_type] = aggregate(subset)
    result["all"] = aggregate(scores)
    return result


# --------------------------------------------------------------------------
# Golden-set loading and validation
# --------------------------------------------------------------------------


def load_questions(
    paths: Sequence[Path],
    verified_only: bool = True,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Load JSONL golden-set files.

    Returns the selected questions and a list of human-readable warnings
    (blank lines, malformed JSON, unknown types, duplicate ids).
    """
    questions: list[dict[str, Any]] = []
    warnings: list[str] = []
    seen_ids: set[str] = set()

    for path in paths:
        with path.open(encoding="utf-8") as handle:
            for lineno, raw in enumerate(handle, start=1):
                line = raw.strip()
                if not line:
                    continue
                where = f"{path.name}:{lineno}"
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as exc:
                    warnings.append(f"{where} malformed JSON ({exc.msg})")
                    continue

                question_id = record.get("id")
                if not question_id:
                    warnings.append(f"{where} missing 'id'")
                    continue
                if question_id in seen_ids:
                    warnings.append(f"{where} duplicate id {question_id!r}")
                    continue

                if record.get("type") not in EVAL_TYPES:
                    warnings.append(
                        f"{where} unknown type {record.get('type')!r} "
                        f"(expected one of {', '.join(EVAL_TYPES)})"
                    )
                    continue
                if not record.get("gold_sections") and record["type"] != "out_of_scope":
                    warnings.append(f"{where} no gold_sections for an in-scope question")
                    continue

                seen_ids.add(question_id)
                if verified_only and not record.get("verified"):
                    continue
                questions.append(record)

    return questions, warnings


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.1f}%"


def _num(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.3f}"


def _dist_cell(distribution: dict[str, float] | None) -> str:
    if not distribution:
        return "n/a"
    return (
        f"n={int(distribution['n'])} "
        f"min={distribution['min']:.3f} "
        f"med={distribution['median']:.3f} "
        f"max={distribution['max']:.3f}"
    )


def render_summary(by_type: dict[str, Aggregate]) -> list[str]:
    """Render the per-type summary table as Markdown lines.

    ``in_scope`` is the slice to quote. ``all`` is kept for completeness and
    includes out-of-scope questions, whose ``section_hit`` is 0 by
    construction.
    """
    lines = [
        "| Slice | n | section_hit@5 | page_hit@5 | MRR | distinct_sections@5 | avg_context_words |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for name, agg in by_type.items():
        page_cell = _pct(agg.page_hit_at_5)
        lines.append(
            f"| {name} | {agg.n} | {_pct(agg.section_hit_at_5)} | {page_cell} | "
            f"{_num(agg.mrr)} | {_num(agg.distinct_sections_at_5)} | "
            f"{agg.avg_context_words:.0f} |"
        )
    return lines


def render_distances(by_type: dict[str, Aggregate]) -> list[str]:
    """Render the in-scope vs out-of-scope cosine distance comparison."""
    overall = by_type["all"]
    if not overall.in_scope_best_distance and not overall.out_of_scope_best_distance:
        overall = by_type["in_scope"] if "in_scope" in by_type else overall
    return [
        "| Distribution | best cosine distance |",
        "| --- | --- |",
        f"| in-scope (all non out_of_scope) | {_dist_cell(overall.in_scope_best_distance)} |",
        f"| out-of-scope | {_dist_cell(overall.out_of_scope_best_distance)} |",
    ]


def render_questions(scores: Sequence[QuestionScore]) -> list[str]:
    """Render the per-question table."""
    lines = [
        "| id | type | hit@5 | rr | distinct | words | best_d | retrieved top section |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for score in scores:
        top = score.returned_sections[0] if score.returned_sections else "-"
        if len(top) > 48:
            top = top[:45] + "..."
        hit = "yes" if score.section_hit else "no"
        best = "n/a" if score.best_distance is None else f"{score.best_distance:.3f}"
        lines.append(
            f"| {score.question_id} | {score.type} | {hit} | "
            f"{score.reciprocal_rank:.2f} | {score.distinct_sections} | "
            f"{score.context_words} | {best} | {top} |"
        )
    return lines
