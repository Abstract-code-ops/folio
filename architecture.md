# Architecture Context

## Stack

|Layer         |Technology                       |Role                                                                         |
|--------------|---------------------------------|-----------------------------------------------------------------------------|
|Frontend      |Next.js 15 + TypeScript          |UI, routing, auth session management                                         |
|Styling       |Tailwind + shadcn/ui             |Component library and design tokens                                          |
|Backend       |FastAPI (Python)                 |All data access, AI pipeline, business logic                                 |
|ORM           |SQLAlchemy + Alembic             |Database models and migrations                                               |
|Auth          |Better Auth (Next.js)            |Sign-in UI, OAuth flows, session creation                                    |
|Auth (API)    |Session lookup via SQLAlchemy    |FastAPI validates requests by querying the Better Auth session table directly|
|Database      |PostgreSQL (Supabase-hosted)     |Relational data, session store, job queue, vector search                     |
| PDF Parsing   | pymupdf4llm                      | Structural PDF parsing, TOC extraction, hierarchy-aware chunking               |
|Vector Search |pgvector (Postgres extension)    |Section and chunk embeddings for similarity search                           |
|Job Queue     |Postgres + dramatiq-pg + Dramatiq|Background ingestion and note session processing                             |
|File Storage  |Supabase Storage                 |Book PDF storage                                                             |
|AI Gateway    |LiteLLM (library mode)           |Unified interface to Gemini, DeepSeek, Cerebras                              |
|AI Providers  |Gemini, DeepSeek, Cerebras       |LLM inference for ingestion metadata, note generation, Q&A                   |
|Observability |PostHog                          |Product analytics and user event tracking                                    |
|Error tracking|Sentry                           |Runtime error reporting for both Next.js and FastAPI                         |

-----

## Repository Structure

```
folio/
├── web/                        # Next.js application
│   ├── app/                    # App router — pages and layouts
│   ├── components/
│   │   ├── ui/                 # shadcn/ui components — do not edit manually
│   │   ├── coverage/           # Coverage map components
│   │   ├── reader/             # PDF reader components
│   │   ├── notes/              # Note session components
│   │   └── chat/               # Q&A components
│   ├── lib/
│   │   ├── api-client.ts       # Typed HTTP client for FastAPI
│   │   ├── auth.ts             # Better Auth configuration
│   │   └── utils.ts            # Shared utilities
│   └── types/                  # TypeScript types shared across the frontend
│
├── api/                        # FastAPI application
│   ├── app/
│   │   ├── routers/            # Route handlers — one file per domain
│   │   │   ├── books.py        # Book selection and ingestion status
│   │   │   ├── coverage.py     # Coverage map retrieval and event emission
│   │   │   ├── notes.py        # Note session submission and note generation
│   │   │   └── qa.py           # Q&A streaming endpoint
│   │   ├── services/           # Business logic — one file per domain
│   │   │   ├── books.py
│   │   │   ├── coverage.py
│   │   │   ├── notes.py
│   │   │   └── qa.py
│   │   ├── pipeline/           # AI pipeline stages
│   │   │   ├── parser.py       # PDF structural parsing and TOC extraction
│   │   │   ├── chunker.py      # Hierarchy-aware chunking
│   │   │   ├── embedder.py     # Chunk and section embedding via LiteLLM
│   │   │   ├── metadata.py     # Section metadata extraction (Pass 1)
│   │   │   ├── note_gen.py     # LLM note generation (Pass 2)
│   │   │   ├── similarity.py   # Cosine similarity pass for note sessions
│   │   │   └── qa_chain.py     # Retrieval and grounded response generation
│   │   ├── workers/            # Dramatiq task definitions
│   │   │   ├── ingest.py       # Book ingestion task
│   │   │   └── note_session.py # Note session similarity pass task
│   │   ├── models/             # SQLAlchemy ORM models
│   │   │   ├── book.py
│   │   │   ├── section.py
│   │   │   ├── chunk.py
│   │   │   ├── note_session.py
│   │   │   ├── coverage_event.py
│   │   │   └── qa_message.py
│   │   └── core/
│   │       ├── config.py       # Environment config and settings
│   │       ├── auth.py         # Session validation against Better Auth table
│   │       ├── db.py           # SQLAlchemy engine and session factory
│   │       ├── litellm.py      # LiteLLM client configuration
│   │       └── storage.py      # Supabase Storage client
│   ├── alembic/                # Database migrations
│   └── main.py                 # FastAPI app entry point
│
├── docker-compose.yml          # Local dev — wires web, api, worker, postgres
└── README.md
```

-----

## System Boundaries

- `web/` — owns the UI, routing, and auth session lifecycle. Makes HTTP
  requests to `api/` for all data. Has no direct database connection.
  The only logic that lives here is presentation, form state, and
  API client calls. Better Auth session cookies are created and managed
  here.
- `api/routers/` — owns request validation, auth verification, and
  response shaping. Routers do not contain business logic. They
  parse the request, verify the session, call a service, and return
  a response.
- `api/services/` — owns business logic and orchestration. Services
  call pipeline modules, emit coverage events, and read/write via
  SQLAlchemy models. Services do not import from routers.
- `api/pipeline/` — owns the AI pipeline stages. Each module is a
  pure function or a small class with a single responsibility. Pipeline
  modules do not import from services or routers. They can be called
  from services or from Dramatiq workers.
- `api/workers/` — owns background task definitions. Workers import
  pipeline modules and services. They are the only place where
  long-running jobs execute. Workers do not handle HTTP requests.
- `api/models/` — owns the SQLAlchemy ORM definitions. Nothing outside
  of `api/` touches the database directly.
- `web/components/ui/` — shadcn/ui generated components. Never edited
  manually. Add new components via the shadcn CLI only.

-----

## Auth and Access Model

- Better Auth runs inside Next.js and owns the sign-in flow, OAuth
  provider callbacks, and session cookie lifecycle.
- Better Auth stores sessions in the `session` table in Postgres,
  managed by Better Auth’s own schema in the same database.
- FastAPI verifies every protected request by extracting the session
  token from the Authorization header and querying the `session` table
  directly via SQLAlchemy. If the session row exists and is not expired,
  the request is authenticated. No JWT secret is shared between
  processes.
- The current authenticated user is resolved to a `user_id` at the
  router level and passed explicitly into service calls. Services and
  pipeline modules never resolve auth themselves.
- Books are a shared global resource. A book record and all its parsed
  sections, chunks, and embeddings are created once and shared across
  all users. If a book is already ingested, no re-ingestion runs.
- Coverage events, note sessions, and Q&A messages are user-scoped.
  No user can read or mutate another user’s records. Ownership is
  enforced in every service call before any read or write.
- The Dramatiq worker processes run without an HTTP request context.
  Jobs are enqueued with a `user_id` and `book_id` as explicit
  parameters — the worker never infers identity from context.

-----

## Storage Model

- **PostgreSQL**: all relational data — users (via Better Auth schema),
  sessions (via Better Auth schema), books, sections, chunks, note
  sessions, coverage events, Q&A messages, job queue (via dramatiq-pg).
- **pgvector (inside PostgreSQL)**: section embeddings for coverage
  similarity matching, chunk embeddings for Q&A retrieval. Stored as
  vector columns on the `section` and `chunk` tables.
- **Section metadata (JSONB column on `section` table)**: structured
  metadata extracted at ingestion time —
  `{learning_objectives, summary, concepts, definitions, equations, examples, exercise_count}`. Written once at ingestion, read at
  note generation time.
- **Supabase Storage**: original book PDF files. Stored once per book,
  referenced by URL in the `book` table. Served to the PDF reader
  in the frontend via a signed URL.
- **In-memory (FastAPI process)**: LiteLLM client instance, active
  streaming connections. Nothing stateful is stored only in memory
  that needs to survive a process restart.

-----

## Background Job Model

- Dramatiq with the `dramatiq-pg` broker. The job queue lives inside
  Postgres — no separate Redis or RabbitMQ process.
- Two worker task types in v1:
  - `ingest_book`: triggered when a book is selected for the first
    time. Runs the full pipeline — parse, chunk, embed, extract
    metadata. Emits section records to the database on completion.
  - `process_note_session`: triggered when a student submits a note
    session. Runs the similarity pass, finds matching sections above
    the threshold, emits `note_matched` coverage events for each.
- Workers run as a separate process (`dramatiq api.app.workers`) but
  share the same codebase and SQLAlchemy models as the FastAPI app.
- The FastAPI router enqueues a job by calling `.send()` on the
  Dramatiq task and returns immediately with a job ID. The frontend
  polls a status endpoint to track progress.

-----

## Coverage Scoring Model

Coverage scores are derived from accumulated events — no LLM is
involved in scoring.

- All user interactions that touch a section emit an event row into
  the `coverage_event` table:
  `{user_id, book_id, section_id, event_type, metadata, created_at}`
- Event types and point values:
  
  |Event type       |Points|Description                                            |
  |-----------------|------|-------------------------------------------------------|
  |`page_viewed`    |1     |Student viewed pages that map to this section          |
  |`note_matched`   |3     |Submitted notes matched this section via similarity    |
  |`notes_generated`|4     |Student generated AI notes for this chapter range      |
  |`qa_asked`       |5     |Student asked a Q&A question answered from this section|
  |`quiz_answered`  |5     |Student answered a quiz question about this section    |
- Coverage score for a section = sum of points from all events for
  that `(user_id, section_id)` pair, capped at 15.
- Visual states:
  
  |Score|State       |Visual treatment|
  |-----|------------|----------------|
  |0    |Uncovered   |Neutral / gray  |
  |1–4  |Mentioned   |Light color     |
  |5–9  |Partial     |Medium color    |
  |10–15|Well covered|Full color      |
- Point values and thresholds are defined in `api/app/core/config.py`
  and tunable without a code change.
- Connective sections (word count < 150 at parse time) are stored with
  `is_connective = true` and rendered with reduced visual weight on
  the map regardless of score.

-----

## AI Usage Model

LLM calls happen in exactly three places:

1. **Ingestion — metadata extraction** (`pipeline/metadata.py`):
   once per section at ingest time. Extracts structured metadata
   from the raw section text using the section skeleton as grounding.
   Runs inside the `ingest_book` Dramatiq worker.
1. **Note generation** (`pipeline/note_gen.py`): once per section
   per user request. Uses the stored section metadata and raw chunk
   text as grounding. Runs in the FastAPI process, streamed
   section by section to the client.
1. **Q&A** (`pipeline/qa_chain.py`): once per question. Retrieves
   top-k chunks from the current section via pgvector, passes them
   with a grounding system prompt to the LLM. Streamed to the client.
   The grounding prompt is a protected invariant — it cannot be
   modified by user input.

LiteLLM routes all three call types across Gemini, DeepSeek, and
Cerebras based on task configuration in `core/litellm.py`. Provider
selection is configurable per task type without code changes.

-----

## Invariants

1. Next.js has no direct database connection. All data access goes
   through FastAPI.
1. Route handlers do not run long-running work synchronously. Any
   operation that takes more than a few hundred milliseconds is
   delegated to a Dramatiq worker and returns a job ID immediately.
1. The Q&A grounding system prompt is defined in `pipeline/qa_chain.py`
   and is never overridden or appended to by user input. Changes to
   it require an explicit code change and must be tested against the
   out-of-scope question eval suite before deployment.
1. Book ingestion runs at most once per book. Before enqueuing an
   `ingest_book` job, the service checks whether the book already
   has a completed ingestion record. If it does, the job is not
   enqueued and the existing data is used.
1. Coverage events are append-only. Events are never updated or
   deleted. Coverage scores are always derived by aggregating the
   event log, never stored as a mutable field.
1. Ownership is verified in the service layer before every read or
   write on user-scoped resources. Routers resolve `user_id` from
   the session and pass it to services explicitly. Services do not
   accept unverified identity.
1. Pipeline modules are stateless and have no imports from routers
   or services. They can be called from both the FastAPI process and
   Dramatiq workers without circular dependencies.
1. `web/components/ui/` is never edited manually. New shadcn
   components are added via the CLI only.
1. All environment-specific configuration — API keys, secrets,
   database URLs, LiteLLM provider config, point value thresholds —
   lives in environment variables read through `core/config.py`.
   No configuration is hardcoded anywhere in the codebase.