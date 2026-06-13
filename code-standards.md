# Code Standards

## General

- Keep modules small and single-purpose. If a file has more than one
  reason to change, split it.
- Fix root causes, do not layer workarounds. If something requires a
  hack to work, resolve the underlying issue first.
- Do not mix unrelated concerns in one component, route, or service.
  UI state, data fetching, and business logic are separate concerns.
- Delete dead code. Do not comment it out.
- Every meaningful implementation change must be reflected in
  `progress-tracker.md` before moving to the next unit.

-----

## TypeScript

- Strict mode is required throughout — both `web/` and `api/` (via
  pyright or mypy equivalent for Python). No exceptions.
- Never use `any` in TypeScript. Use explicit interfaces, narrowly
  scoped generics, or `unknown` with type narrowing.
- Validate all unknown external input at system boundaries before
  trusting it — API responses from FastAPI, URL params, form data.
  Use `zod` for runtime validation on the Next.js side.
- All FastAPI response shapes must have a corresponding TypeScript
  type in `web/types/`. These are the contract between the two
  processes and must be kept in sync manually.
- Use `async/await` throughout. No `.then()` chains.
- `params` and `searchParams` in Next.js 16 page components are
  async — always `await` them. Sync access is removed and will throw.

-----

## Next.js 16

- Use the App Router exclusively. No Pages Router.
- Default to server components. Add `"use client"` only when the
  component requires browser APIs, event handlers, or React hooks
  that cannot run on the server.
- Caching is explicit and opt-in via the `"use cache"` directive.
  Do not assume any route or component is cached. User-scoped data
  (coverage maps, note sessions, Q&A history) must never use
  `"use cache"` — it is dynamic by definition.
- Use `updateTag()` in Server Actions when a mutation must be
  immediately visible to the user in the same request — for example,
  after a note session is submitted and the coverage map must reflect
  the new state.
- Use `revalidateTag(tag, 'max')` for shared, non-user-specific data
  that can tolerate eventual consistency — for example, book metadata
  from the library.
- Use `proxy.ts` (not `middleware.ts`) for all request interception
  at the network boundary. `middleware.ts` is deprecated in Next.js 16.
- The React Compiler is enabled. Do not add manual `useMemo`,
  `useCallback`, or `React.memo` unless profiling shows a specific
  regression the compiler did not catch. Let the compiler handle
  memoization.
- `async params` and `async searchParams` are required in all page
  components and route handlers. Always destructure after awaiting:
  `const { id } = await params`.
- Parallel route slots require explicit `default.js` files. Any
  parallel route added must include a `default.js` that returns
  `null` or calls `notFound()`.
- Keep route handlers focused on a single responsibility: parse
  input, call the FastAPI client, return the response. No business
  logic in route handlers.
- Streaming responses from FastAPI (note generation, Q&A) must be
  proxied through a Next.js route handler using `ReadableStream` —
  do not expose the FastAPI URL to the client directly.

-----

## Python / FastAPI

- Python 3.12+ required. Use type hints throughout — all function
  signatures, all class attributes.
- Use `async def` for all route handlers and service functions.
  Blocking I/O (file reads, synchronous library calls) must be
  wrapped in `asyncio.to_thread`.
- Routers validate and parse input, verify auth, call one service
  function, and return a response. No logic beyond this.
- Services orchestrate business logic and call pipeline modules or
  SQLAlchemy models. Services do not import from routers.
- Pipeline modules are pure functions or stateless classes. They
  accept explicit arguments and return explicit values. No side
  effects, no imports from services or routers.
- All database access goes through SQLAlchemy sessions obtained from
  `core/db.py`. Never construct raw SQL strings — use the ORM or
  SQLAlchemy Core with bound parameters.
- Pydantic models are required for all request bodies and response
  shapes. FastAPI’s automatic validation is not optional.
- Use `HTTPException` with explicit status codes for all error
  responses. Never return a 200 with an error payload.
- LiteLLM is called only from pipeline modules — never from routers
  or services directly.

-----

## Styling

- Use Tailwind utility classes exclusively. No inline `style` props
  unless animating a dynamic value that cannot be expressed as a
  class (e.g. a coverage percentage as a CSS custom property).
- Use CSS custom property tokens defined in `ui-context.md` for
  colors. No hardcoded hex values anywhere in component code.
- Follow the border radius scale defined in `ui-context.md`. Do not
  introduce new radius values.
- The AI panel, note input, and coverage map are secondary surfaces.
  The PDF reader is the primary surface. Layout must reflect this
  hierarchy — reader gets the dominant space by default.

-----

## API Client (`web/lib/api-client.ts`)

- All HTTP calls from Next.js to FastAPI go through the typed API
  client. No `fetch` calls outside of this module.
- The API client attaches the Better Auth session token to every
  request. Route handlers and components do not handle auth headers
  manually.
- Streaming endpoints (note generation, Q&A) are handled via
  `ReadableStream` in the API client and exposed as async generators
  to callers.
- The base URL is read from an environment variable. It is never
  hardcoded.

-----

## API Routes (FastAPI)

- Validate and parse all request input with Pydantic before any
  logic runs.
- Enforce auth by calling the session lookup in `core/auth.py` at
  the top of every protected route handler. No route skips this.
- Verify ownership in the service layer before any read or write on
  user-scoped resources. Routers pass `user_id` to services
  explicitly — services never resolve identity themselves.
- Return consistent response shapes. Success responses follow the
  Pydantic model. Error responses use `HTTPException`.
- Long-running operations return a job ID immediately and a
  `/status/{job_id}` endpoint for polling. They never block the
  response.

-----

## Database and Storage

- Metadata and relational data belong in PostgreSQL via SQLAlchemy
  models.
- Book PDF files belong in Supabase Storage. The database stores
  only the storage reference URL.
- Vector embeddings belong in pgvector columns on the `section` and
  `chunk` tables. Do not store embeddings in a separate service.
- Section metadata (learning objectives, concepts, definitions,
  equations, examples, exercise count) belongs in a JSONB column
  on the `section` table — written once at ingestion, never updated.
- Coverage events are append-only. Never update or delete a coverage
  event row. Coverage scores are always derived by aggregation.
- Do not store large generated content (full note generation output)
  directly in the database as a single blob. Store per-section note
  records linked by `section_id`.
- All schema changes go through Alembic migrations. Never modify the
  database schema manually.

-----

## Background Workers (Dramatiq)

- Workers import from `pipeline/` and `services/` only. They do not
  import from `routers/`.
- Every worker task accepts explicit `user_id` and `book_id`
  parameters. Workers never infer identity from context.
- Workers must be idempotent — running the same task twice must not
  corrupt data. Check for existing records before writing.
- Task failures must be logged to Sentry with the task name,
  parameters, and full traceback.

-----

## Observability

- PostHog events are emitted from the Next.js client for all user
  interactions that map to coverage events — page views, note
  session submission, note generation requests, Q&A questions asked.
  These are the same semantic events emitted to the coverage event
  table in the backend.
- Sentry is configured in both the Next.js app and the FastAPI app.
  Unhandled exceptions in both processes are reported automatically.
- Sentry is also configured in the Dramatiq worker process. Task
  failures are captured with full context.
- Do not log personally identifiable information (PII) to PostHog,
  Sentry, or any log output. User IDs are acceptable. Email
  addresses, note content, and Q&A messages are not.

-----

## File Organisation

- `web/app/` — Next.js App Router pages, layouts, and route handlers
  only. No shared logic.
- `web/components/ui/` — shadcn/ui generated components. Never edited
  manually. Add new components via the shadcn CLI only.
- `web/components/[feature]/` — feature-specific components. One
  folder per product domain: `coverage/`, `reader/`, `notes/`,
  `chat/`.
- `web/lib/` — shared utilities, the API client, and Better Auth
  configuration. No React components here.
- `web/types/` — TypeScript type definitions that mirror FastAPI
  Pydantic response models. One file per domain.
- `api/app/routers/` — one file per domain. Route handlers only.
- `api/app/services/` — one file per domain. Business logic only.
- `api/app/pipeline/` — one file per pipeline stage. Stateless,
  no imports from services or routers.
- `api/app/workers/` — Dramatiq task definitions only. One file per
  background job group.
- `api/app/models/` — SQLAlchemy ORM models only. One file per table
  group.
- `api/app/core/` — application-wide configuration, auth session
  lookup, database session factory, LiteLLM client, storage client.
  No domain logic here.