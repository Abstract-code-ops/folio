# Retrieval eval harness (plan unit U1)

Answers one question: **did that pipeline change help or hurt?** Nothing after
U1 should ship without a before/after number from here.

The runner never calls an LLM. A full run costs one embedding per question and
nothing else, so it is cheap enough to run on every pipeline change.

## Files

| Path | Purpose |
| --- | --- |
| `api/evals/metrics.py` | Pure scoring and aggregation. No database, no network, no LLM. |
| `api/evals/runner.py` | CLI. Calls the real `retrieve_top_chunks` and `build_citations`. |
| `api/evals/fixtures/*.jsonl` | Golden question sets, one JSON object per line. |
| `api/tests/evals/test_metrics.py` | Pytest gate on fixtures. Runs without Postgres or Ollama. |
| `docs/pipeline-eval-log.md` | The baseline and every change under test. |

## Running

Inside the api container (the database and Ollama are reachable there):

```bash
# verified questions only - the default, and the only mode you should quote
docker exec folio-api-1 python3 -m evals.runner

# sanity-check the drafted set (gold sections not yet hand-checked)
docker exec folio-api-1 python3 -m evals.runner --include-unverified

# narrow a run while iterating
docker exec folio-api-1 python3 -m evals.runner --book sicp --limit 10
docker exec folio-api-1 python3 -m evals.runner --json
```

Append the result to `docs/pipeline-eval-log.md` with the date, the commit, and
the change under test.

## The golden set

One JSON object per line:

```json
{
  "id": "ddia-007",
  "book_id": "0052b432-55e3-4945-9b5c-60e060f2b7b9",
  "type": "definition | ambiguous | multi_section | broad | followup | out_of_scope",
  "question": "...",
  "history": [],
  "gold_sections": ["Change data capture"],
  "gold_pages": [461, 463],
  "verified": false
}
```

Rules that matter:

- **`verified` is the contract.** Questions ship as `false`. The runner reports
  only on `verified: true`. An agent may draft questions and derive gold
  sections from real headings, but only the curator can confirm that a section
  actually answers the question - flip it to `true` after checking the page in
  the reader.
- **`gold_sections` are exact stored headings** (`section.heading`), not
  numbered forms like `"3.2 B-Trees"`. Matching normalises whitespace, dashes
  and case, so em dashes and en dashes are interchangeable.
- **`gold_pages` are inclusive bounds** `[low, high]` taken from the section's
  real page range in the database - not invented, and not hand-checked answer
  locations. Tighten them to the actual answer pages when you verify.
- **No passages, ever.** The set holds questions, section names and page
  numbers only.
- **`history` is user turns only.** No assistant text is stored, because an
  invented assistant answer would be a fabricated claim about the book.

Distribution target per book: ~40 questions, at least 10 `out_of_scope`, at
least 5 `followup` with a short history.

## Current state

- `fixtures/ddia.jsonl` - 40 questions (DDIA, 187 sections).
- `fixtures/sicp.jsonl` - 40 questions (SICP, 140 sections).
- **0 verified.** Every number in the log today is marked DRAFT.
- *Just Use Postgres* has no fixture: it has 0 sections in the database
  (`ingestion_status = not_started`), so there is nothing to ask about. Add a
  set once the curator ingests it.

## Metrics

| Metric | Meaning |
| --- | --- |
| `section_hit@5` | A gold section is among the five retrieved chunks' sections. |
| `page_hit@5` | A gold page falls inside a retrieved chunk's page range. `n/a` until chunks carry page ranges (U6 + U7). |
| `mrr` | Reciprocal rank of the first chunk from a gold section; 0.0 on a miss. |
| `distinct_sections@5` | How many different sections the five chunks cover. Low means the five slots are spent inside one section. |
| `avg_context_words` | Word count of the assembled grounding context. This is the prompt cost per question. |
| `best_distance` | Smallest cosine distance among the five chunks, used to separate in-scope from out-of-scope questions. |

`in_scope` is the slice to quote. The `all` slice includes `out_of_scope`
questions, whose `section_hit` is 0 by construction, so it always reads lower.

## Limitations

- A gold heading that matches more than one section in a book makes
  `section_hit` generous. The runner warns; no current gold heading is
  ambiguous.
- One embedding call is used to rank (inside `retrieve_top_chunks`) and one to
  measure distances, so a run makes two per question. Worth folding together
  when U8 touches the embedding path.
- The optional LLM-judge faithfulness pass described in the plan is **not
  implemented**. Everything here is retrieval-only.
- Unverified gold makes the whole set directional. Fix the set before trusting
  small deltas.
