# AI Workflow Rules

## Approach

Build Folio incrementally using a spec-driven workflow. The context files
(`project-overview.md`, `architecture.md`, `code-standards.md`,
`ui-context.md`, `progress-tracker.md`) define what to build, how to build
it, and the current state of progress. Always implement against these specs.

When a requirement is ambiguous, make the most conservative inference that
is consistent with the existing specs, implement it, and log the inference
as an open question in `progress-tracker.md`. Do not block or ask for
clarification mid-session — log and continue.

When a requirement is missing entirely, add it as an open question in
`progress-tracker.md` and skip the affected behaviour until the question
is resolved in the relevant context file.

-----

## Scoping Rules

- Work on one feature unit at a time.
- A feature unit is a single, end-to-end verifiable increment: one endpoint,
  one service function, one pipeline stage, one worker task, one UI component.
- Prefer the smallest increment that can be verified over a larger change that
  cannot be tested in isolation.
- Do not combine unrelated concerns in a single implementation step.

-----

## Architecture Layer Boundaries

Folio’s architecture defines four explicit backend layers and one frontend
layer. These are the canonical split boundaries:

|Layer             |Location           |
|------------------|-------------------|
|Route handlers    |`api/app/routers/` |
|Business logic    |`api/app/services/`|
|AI pipeline stages|`api/app/pipeline/`|
|Background workers|`api/app/workers/` |
|Frontend          |`web/`             |

**An implementation step must not cross more than one of these boundaries.**

If a feature requires changes in two or more layers, split it into one unit
per layer. Each unit is implemented and verified independently before the
next begins.

Examples of required splits:

- “Add the note session endpoint” (router) and “add the similarity pipeline
  pass” (pipeline) are two separate units even though they are part of the
  same feature.
- “Add a coverage event query” (service) and “render coverage state on the
  map” (frontend) are two separate units.
- Any new FastAPI endpoint and its corresponding TypeScript type update
  are treated as one atomic unit within the frontend layer — see the
  Type Contract rule below.

-----

## When to Split Work

Split an implementation step if it:

- Touches more than one architecture layer boundary (see above).
- Combines a schema change (new Alembic migration) with application logic
  that depends on it — migrate first, verify, then implement the logic.
- Includes behaviour that is not defined in the context files. Do not
  implement undefined behaviour speculatively; log the gap and stop at
  the boundary of what is defined.
- Cannot be verified end to end within its own scope without completing
  another unrelated change first.

-----

## Protected Files

Do not modify the following files unless explicitly instructed:

- `web/components/ui/*` — shadcn/ui generated components. Add new
  components via the shadcn CLI only. Never edit these files by hand.
- `alembic/versions/*` — generated migration files. The agent may generate
  a new migration file but must never edit an existing one.
- The Q&A grounding system prompt in `api/app/pipeline/qa_chain.py` —
  this is a protected invariant defined in `architecture.md`. Changes
  require explicit instruction and must be tested against the out-of-scope
  question eval suite before deployment.

-----

## Type Contract Rule

FastAPI endpoints and their corresponding TypeScript types are one atomic unit.

Whenever a new FastAPI endpoint is added or an existing endpoint’s response
shape changes:

1. Update or create the Pydantic response model in the relevant
   `api/app/routers/` or `api/app/services/` file.
1. In the same implementation step, update the corresponding TypeScript
   type in `web/types/`.
1. Update `web/lib/api-client.ts` if the endpoint is new or its signature
   changed.

The agent must never add a FastAPI endpoint without completing all three
steps. Partial updates that leave the type contract out of sync are not
permitted.

-----

## Handling Missing Requirements

- Do not invent product behaviour not defined in the context files.
- If a requirement is ambiguous, make the most conservative inference
  consistent with the specs, implement it, and log the decision in
  `progress-tracker.md` under **Open Questions**.
- If a requirement is missing, add it as an open question in
  `progress-tracker.md` and do not implement the affected behaviour
  until the question is resolved in the relevant context file.
- Never resolve an ambiguity by checking general knowledge or
  convention alone. The context files are the source of truth.

-----

## Progress Tracking

Update `progress-tracker.md` after every file written — not just after
every milestone. Sessions may end at any point. The tracker must always
reflect the exact state of the codebase so work can resume without
re-reading source files.

After writing each file, record:

- Which file was written or modified.
- What it implements and why.
- Any open questions or conservative inferences made during that step.

Update the **Completed**, **In Progress**, and **Next Up** sections
so the current state is unambiguous at the start of the next session.

-----

## Keeping Context Files in Sync

Update the relevant context file whenever an implementation decision changes:

- A new architecture boundary or system component → `architecture.md`
- A storage model decision (new table, new column, new index) → `architecture.md`
- A new code convention or standard → `code-standards.md`
- A change to the feature scope → `project-overview.md`
- A UI token, layout pattern, or component decision → `ui-context.md`

Context file updates are part of the implementation step, not an optional
follow-up.

-----

## Before Moving to the Next Unit

All of the following must be true before starting the next feature unit:

1. The current unit works end to end within its defined scope.
1. No invariant defined in `architecture.md` was violated.
1. `progress-tracker.md` reflects every file written in this unit.
1. All of the following build gates pass:
- `npm run build` succeeds in `web/`
- `pytest` passes in `api/`
- No Alembic migration conflicts exist
- If the unit added or modified a Dramatiq worker: `dramatiq api.app.workers`
  starts without import errors

Do not proceed to the next unit if any gate fails. Fix the failure first.