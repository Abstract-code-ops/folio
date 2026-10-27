"""Check answer grounding on out-of-scope questions with a real model call.

Plan unit U9 acceptance: after changing the context format, confirm that answers
still refuse when the book does not cover the question, and do not start drawing
on outside knowledge.

This costs real tokens -- one generation per question -- so it is a small,
curator-run sample, not part of the eval harness (which makes zero LLM calls).

Usage::

    docker exec folio-api-1 python3 /app/scripts/check_grounding.py
    docker exec folio-api-1 python3 /app/scripts/check_grounding.py --limit 5

Each line reports PASS when the answer looks like a refusal, REVIEW otherwise,
with the first part of the answer so you can judge it yourself. Nothing is
written to the database.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from pathlib import Path

# Make ``app`` and ``evals`` importable when run as a plain file.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.db import AsyncSessionLocal  # noqa: E402
from app.pipeline.qa_chain import (  # noqa: E402
    answer_question_stream,
    build_context,
)
from app.services.qa import expand_context, retrieve_top_chunks  # noqa: E402
from evals.metrics import load_questions  # noqa: E402

FIXTURES = Path(__file__).resolve().parent.parent / "evals" / "fixtures"

# Phrases that indicate a refusal rather than an invented answer.
REFUSAL_MARKERS = (
    "not covered",
    "isn't covered",
    "is not in this",
    "does not cover",
    "doesn't cover",
    "not discussed",
    "no information",
    "not addressed",
)


async def _answer(db, book_id: uuid.UUID, question: str) -> tuple[str, int]:
    """Run the real answer path and return (answer text, matched chunks)."""
    hits = await retrieve_top_chunks(db, book_id, question)
    passages = await expand_context(db, hits)
    context = build_context([(p, p.distance or 0.0) for p in passages])

    answer = ""
    async for event_bytes in answer_question_stream(
        question=question, context=context, summary=None, history=None
    ):
        event = json.loads(event_bytes)
        if event.get("type") == "token":
            answer += event.get("text", "")
    return answer, len(hits)


async def run(limit: int) -> int:
    paths = sorted(FIXTURES.glob("*.jsonl"))
    questions, _warnings = load_questions(paths, verified_only=True)
    out_of_scope = [q for q in questions if q["type"] == "out_of_scope"][:limit]

    if not out_of_scope:
        print("No out_of_scope questions in the verified set.")
        return 1

    print(f"Checking {len(out_of_scope)} out-of-scope question(s) with a real model call.")
    print("")

    refusals = 0
    async with AsyncSessionLocal() as db:
        for question in out_of_scope:
            answer, hit_count = await _answer(
                db, uuid.UUID(question["book_id"]), question["question"]
            )
            lowered = answer.lower()
            refused = any(marker in lowered for marker in REFUSAL_MARKERS)
            refusals += 1 if refused else 0

            print(f"[{'PASS' if refused else 'REVIEW'}] {question['id']}")
            print(f"  question:  {question['question']}")
            print(f"  retrieved: {hit_count} chunk(s)")
            print(f"  answer:    {answer.strip()[:220]!r}")
            print("")

    print(f"{refusals}/{len(out_of_scope)} refused as expected.")
    if refusals < len(out_of_scope):
        print(
            "REVIEW means the answer did not contain a refusal phrase -- read the "
            "answer above and judge whether it drew on outside knowledge."
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Spot-check refusal behaviour with a real model call."
    )
    parser.add_argument(
        "--limit", type=int, default=3, help="how many questions to sample (default 3)"
    )
    args = parser.parse_args(argv)
    return asyncio.run(run(args.limit))


if __name__ == "__main__":
    raise SystemExit(main())
