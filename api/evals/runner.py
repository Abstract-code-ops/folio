"""Retrieval eval runner (plan unit U1).

Runs the golden question set through the **real** retrieval path
(`services.qa.retrieve_top_chunks`) and the real citation builder
(`services.qa.build_citations`), then scores the results. It never calls
an LLM, so a full run costs one embedding per question and nothing else.

What it does not do: no generation, no faithfulness judge, no database
writes, no schema changes. Metrics only.

Usage (inside the api container)::

    docker exec folio-api-1 python3 -m evals.runner
    docker exec folio-api-1 python3 -m evals.runner --include-unverified
    docker exec folio-api-1 python3 -m evals.runner --book sicp --limit 10
    docker exec folio-api-1 python3 -m evals.runner --json

By default only questions with ``"verified": true`` are scored, per the
unit spec. ``--include-unverified`` scores the drafted set as well and
labels the output **DRAFT**, because unverified gold sections make the
numbers directional only.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any, Sequence

# Running ``python3 /app/evals/runner.py`` puts evals/ on sys.path; add the
# project root so ``app.*`` resolves in both invocation styles.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from app.core.db import AsyncSessionLocal  # noqa: E402
from app.models.book import Book  # noqa: E402
from app.models.section import Section  # noqa: E402
from app.pipeline.qa_chain import build_context  # noqa: E402
from app.services.qa import (  # noqa: E402
    TOP_K_CHUNKS,
    build_used_citations,
    expand_context,
    retrieve_top_chunks,
)
from evals.metrics import (  # noqa: E402
    QuestionScore,
    RetrievedChunk,
    aggregate_by_type,
    load_questions,
    normalise_heading,
    render_distances,
    render_questions,
    render_summary,
    score_question,
)

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


async def _gold_warnings(
    db: AsyncSession, questions: Sequence[dict[str, Any]]
) -> list[str]:
    """Check every gold heading resolves to at least one section in its book."""
    book_ids = {uuid.UUID(q["book_id"]) for q in questions}
    rows = (
        await db.execute(
            select(Section.book_id, Section.heading).where(
                Section.book_id.in_(list(book_ids))
            )
        )
    ).all()

    by_book: dict[uuid.UUID, list[str]] = {}
    for book_id, heading in rows:
        by_book.setdefault(book_id, []).append(normalise_heading(heading))

    warnings: list[str] = []
    for question in questions:
        book_id = uuid.UUID(question["book_id"])
        headings = by_book.get(book_id, [])
        for gold in question.get("gold_sections", []):
            normalised = normalise_heading(gold)
            matches = sum(1 for h in headings if h == normalised)
            if matches == 0:
                warnings.append(
                    f"{question['id']}: gold section {gold!r} does not exist in this book"
                )
            elif matches > 1:
                warnings.append(
                    f"{question['id']}: gold section {gold!r} matches {matches} "
                    f"sections (hit counts any; add pages to disambiguate)"
                )
    return warnings


async def evaluate(
    db: AsyncSession, questions: Sequence[dict[str, Any]]
) -> list[QuestionScore]:
    """Score every question against the live retrieval path."""
    scores: list[QuestionScore] = []

    for question in questions:
        book_id = uuid.UUID(question["book_id"])

        # The real retrieval path, with real cosine distances.
        hits = await retrieve_top_chunks(db, book_id, question["question"])

        retrieved = [
            RetrievedChunk(
                chunk_id=str(chunk.id),
                section_id=str(chunk.section_id),
                section_heading=chunk.section.heading,
                chunk_index=chunk.chunk_index,
                word_count=len((chunk.content or "").split()),
                page_start=getattr(chunk, "page_start", None),
                page_end=getattr(chunk, "page_end", None),
                distance=distance,
            )
            for chunk, distance in hits
        ]

        # Context cost includes any expansion, so the eval sees the real prompt.
        passages = await expand_context(db, hits)
        # The real citation builder, exercised so a break in the citation
        # contract shows up here rather than in the UI.
        build_used_citations("[1]", passages)
        context = build_context(
            [(passage, passage.distance or 0.0) for passage in passages]
        )
        scores.append(
            score_question(question, retrieved, len(context.split()))
        )

    return scores


def render_report(
    *,
    scores: Sequence[QuestionScore],
    by_type: dict[str, Any],
    question_total: int,
    verified_total: int,
    draft_mode: bool,
    warnings: Sequence[str],
) -> str:
    """Render the full Markdown report."""
    lines: list[str] = []
    lines.append("# Retrieval eval")
    lines.append("")
    lines.append(
        f"- mode: {'DRAFT - gold sections unverified' if draft_mode else 'verified set only'}"
    )
    lines.append(f"- questions scored: {len(scores)}")
    lines.append(f"- questions in fixture set: {question_total}")
    lines.append(f"- questions marked verified: {verified_total}")
    lines.append(f"- top-k: {TOP_K_CHUNKS}")
    lines.append("- LLM calls: 0")
    lines.append("")

    if draft_mode:
        lines.append(
            "> DRAFT: this run includes questions whose gold sections have not "
            "been checked by hand. Treat the numbers as directional only."
        )
        lines.append("")

    if not scores:
        lines.append(
            "No questions scored. Either no question set `verified` yet, or the "
            "fixtures are missing. Run with `--include-unverified` to sanity "
            "check the drafted set."
        )
        return "\n".join(lines)

    lines.append("## Summary")
    lines.append("")
    lines.extend(render_summary(by_type))
    lines.append("")
    lines.append("## In-scope vs out-of-scope distance")
    lines.append("")
    lines.append(
        "Smallest cosine distance per question. If the two distributions "
        "overlap, no single threshold separates them and U8 must not enable "
        "`MAX_DISTANCE`."
    )
    lines.append("")
    lines.extend(render_distances(by_type))
    lines.append("")
    lines.append("## Per question")
    lines.append("")
    lines.extend(render_questions(scores))
    lines.append("")

    if warnings:
        lines.append("## Warnings")
        lines.append("")
        lines.extend(f"- {warning}" for warning in warnings)
        lines.append("")

    return "\n".join(lines)


async def _run(args: argparse.Namespace) -> int:
    paths = sorted(FIXTURES_DIR.glob("*.jsonl"))
    if not paths:
        print(f"No fixture files in {FIXTURES_DIR}", file=sys.stderr)
        return 1

    selected, warnings = load_questions(paths, verified_only=not args.include_unverified)
    all_questions, _ = load_questions(paths, verified_only=False)

    if args.book:
        needle = args.book.casefold()
        selected = [q for q in selected if needle in q["id"].casefold() or needle in q["book_id"]]
    if args.limit:
        selected = selected[: args.limit]

    verified_total = sum(1 for q in all_questions if q.get("verified"))

    async with AsyncSessionLocal() as db:
        # Human-readable book names in the warnings and report.
        books = {
            str(book.id): book.title
            for book in (await db.execute(select(Book))).scalars()
        }

        if selected:
            warnings.extend(await _gold_warnings(db, selected))
            scores = await evaluate(db, selected)
            by_type = aggregate_by_type(scores)
        else:
            scores = []
            by_type = {}

    if args.json:
        payload = {
            "mode": "draft" if args.include_unverified else "verified",
            "llm_calls": 0,
            "books": books,
            "questions_in_fixture_set": len(all_questions),
            "questions_verified": verified_total,
            "questions_scored": len(scores),
            "warnings": warnings,
            "per_question": [
                {
                    "id": s.question_id,
                    "type": s.type,
                    "section_hit": s.section_hit,
                    "page_hit": s.page_hit,
                    "reciprocal_rank": s.reciprocal_rank,
                    "distinct_sections": s.distinct_sections,
                    "context_words": s.context_words,
                    "best_distance": s.best_distance,
                    "returned_sections": s.returned_sections,
                }
                for s in scores
            ],
        }
        print(json.dumps(payload, indent=2))
        return 0

    print(
        render_report(
            scores=scores,
            by_type=by_type,
            question_total=len(all_questions),
            verified_total=verified_total,
            draft_mode=args.include_unverified,
            warnings=warnings,
        )
    )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Parse arguments and run the harness."""
    parser = argparse.ArgumentParser(description="Retrieval eval harness (no LLM calls)")
    parser.add_argument(
        "--include-unverified",
        action="store_true",
        help="also score questions whose gold sections have not been checked",
    )
    parser.add_argument("--book", help="only questions whose id contains this text")
    parser.add_argument("--limit", type=int, default=0, help="cap the number of questions")
    parser.add_argument("--json", action="store_true", help="emit JSON instead of Markdown")
    return asyncio.run(_run(parser.parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
