# Folio — Session Log & Handoff

_Last updated: end of this session. Read this first next session._

---

## TL;DR — current state

- **Frontend**: library + reader + coverage map + chat + notes all built and wired to the live API.
- **Notes**: full feature — note documents (blocks), a Tiptap editor with autosave, citation chips that jump the PDF, per-section backlinks, and topic → note generation. Migration `0006` applied. See §12 and `docs/notes-design-notes.md`.
- **PDF viewer**: switched to **EmbedPDF** (`@embedpdf/react-pdf-viewer`) — working, feature-rich (highlight, search, thumbnails, scroll, page count).
- **Chat/Q&A**: working end-to-end — VoidAI (`gpt-oss-20b`), pgvector `<=>` retrieval, Nomic/Ollama embeddings.
- **Production build** still fails on a pre-existing **Sentry** issue (dev mode works).
- **Auth** is temporarily disabled (anonymous user fallback).

---

## 1. How to run (the important part)

### Start containers
```bash
docker compose up -d web api      # NOT the worker (see memory note)
```

### Start dev server — MUST use the env override
```bash
docker exec -d -e NEXT_PUBLIC_API_URL=/api/proxy folio-web-1 npm run dev
```

### Start ngrok
```bash
docker exec -d folio-web-1 ngrok http 3000 --log=stdout
```

**Public URL:** https://doze-computer-dragging.ngrok-free.dev (fixed)

### Kill all next servers (before restarting)
```bash
docker exec folio-web-1 sh -c 'for p in /proc/*/cmdline; do pid=$(echo $p | cut -d/ -f3); cmd=$(cat $p 2>/dev/null | tr "\0" " "); case "$cmd" in *next*) kill $pid;; esac; done'
```

### Why the env override is mandatory
The container has `NEXT_PUBLIC_API_URL=http://api:8000` baked in from `docker-compose.yaml`.
Next.js inlines every `NEXT_PUBLIC_*` var into the browser bundle. The browser cannot reach
`http://api:8000` (Docker-internal hostname) → "Couldn't load your library".
Override to `/api/proxy` → browser calls the Next.js route handler (same origin) → forwards to the API inside Docker.

**Permanent fix (not yet done):** remove the `NEXT_PUBLIC_API_URL` line from `docker-compose.yaml`
so the code's fallback (`?? "/api/proxy"`) is used and the `-e` flag is never needed again.

---

## 2. Container / memory notes

- `docker-compose.yaml` definnes **3 services**: `web`, `api`, `worker`.
- Both `api` and `worker` share `api/Dockerfile.dev` and `entrypoint.sh`, which **starts Ollama and loads nomic-embed-text**.
- Running `docker compose up` (all 3) starts **two Ollama instances** → exhausts RAM (7.6 GB box) → OOM crash.
- **Always start only `web api`** unless actively testing note sessions:
  ```bash
  docker compose up -d web api
  ```
- `web` container's main process is `sleep infinity`; you exec into it and run `next dev` / `ngrok` manually.

---

## 3. Architecture — how data flows

```
Browser ──► Next.js (folio-web-1) ──► FastAPI (folio-api-1) ──► Postgres/Supabase
              │                            │
              │  /api/proxy/[...path]      │  (Docker network, http://api:8000)
              │  /api/pdf?url=...          │
              └── same-origin proxy ───────┘
```

- **`/api/proxy/[...path]`** (`web/app/api/proxy/[...path]/route.ts`) — forwards GET + POST (incl. streaming NDJSON) to the API.
- **`/api/pdf?url=...`** (`web/app/api/pdf/route.ts`) — streams PDF bytes with **Range support** (for pdf.js / PDFium byte ranges).
- API base for the browser is `/api/proxy` (via the env override).

---

## 4. What was built this session

### Frontend components
| Component | File | Status |
|-----------|------|--------|
| Library page | `web/app/page.tsx` | ✅ Live API + Zustand cache |
| Reader page | `web/app/reader/page.tsx` | ✅ Live data, shadcn Tabs + resizable panel |
| Coverage map | `web/components/coverage/*` | ✅ Modular brain map (bumpy outline, chapter nodes, ambient network) |
| PDF viewer | `web/components/reader/PdfViewer.tsx` | ✅ EmbedPDF integration |
| Chat panel | `web/components/chat/ChatPanel.tsx` | ✅ UI done — backend broken |
| Notes panel | `web/components/notes/NotesPanel.tsx` | ✅ UI done |
| Books cache | `web/lib/store.ts` | ✅ Zustand (`fetchBooks`, avoids refetch) |

### Layout
- **Desktop (≥1024px):** shadcn **Tabs** on top; **resizable** left panel (drag, max 50%) + PDF. `ResizablePanelGroup` from shadcn.
- **Mobile (<1024px):** PDF full screen; bottom nav opens a shadcn **Sheet** (90vh).
- **`react-resizable-panels` pinned to v2** (`@2.1.9`) — v4 changed the API and breaks shadcn's `resizable.tsx`.

### shadcn components installed
`sheet`, `tabs`, `scroll-area`, `resizable` → `web/components/ui/`

### Backend changes
- `storage_url` added to `BookResponse` (for the PDF viewer).
- `GET /notes` endpoint + `list_note_sessions()` service.
- **Auth made optional:** `get_current_user()` returns anonymous user ID `00000000-0000-0000-0000-000000000001` when no token. (Temporary.)

---

## 5. PDF viewer — the EmbedPDF integration

Replaced the hand-rolled pdf.js viewer (and before that react-pdf v9/v10, and a native iframe) with **EmbedPDF**.

**Package:** `@embedpdf/react-pdf-viewer` (v2.15.1) → wraps `@embedpdf/snippet` → **PDFium WASM** engine.

**Component** (`web/components/reader/PdfViewer.tsx`):
```tsx
<PDFViewer
  config={{
    src: proxiedUrl,                 // /api/pdf?url=...
    theme: { preference: "dark", dark: { accent: { primary: "#7C5CFC" } } },
    tabBar: "never",
  }}
  onReady={handleReady}
/>
```
- **WASM loads from jsDelivr CDN by default** (`cdn.jsdelivr.net/npm/@embedpdf/pdfium@2.15.1/dist/pdfium.wasm`) — no build-copy step.
- Page tracking via the `scroll` plugin: `registry.getPlugin("scroll")?.provides?.().onPageChange(...)`.
- Jump-to-page via `scrollToPage({ pageNumber, behavior: "smooth" })`.

**Features for free:** highlight/annotation, search, thumbnails, zoom, bookmarks/TOC, page nav.

**Known non-issue:** searching logs `Error during search: {}` (a task-abort artifact) but **still works**. Ignore it.

**Self-host option (future):** copy `pdfium.wasm` → `/public`, set `config.wasmUrl = "/pdfium.wasm"`.

---

## 6. Chat / Q&A — working

Chat is wired end-to-end: ChatPanel → `apiClient.askQuestion()` → `POST /qa/{book_id}` → `qa.py` router → `qa_chain.py`.

- **Model**: VoidAI (`gpt-oss-20b`), real token streaming.
- **Retrieval**: pgvector `<=>` cosine search against chunk embeddings.
- **Embeddings**: Nomic via Ollama (`nomic-embed-text`, 768-dim).
- **Prereqs**: API container up (Ollama running for `embed_text`, `VOID_API_KEY` set), and chunks have embeddings (SICP does).

---

## 7. Other known issues / outstanding

| # | Issue | Notes |
|---|-------|-------|
| 1 | Sentry breaks production build | `@sentry/nextjs` installed but no `sentry.*.config.ts` files; `<Html>` prerender error on `/404`, `/500`. Dev mode unaffected. |
| 2 | Auth disabled | `get_current_user()` returns anonymous ID. Revert when wiring Better Auth. |
| 3 | Env override needed every start | See §1 permanent fix |
| 4 | `worker` doubles Ollama | See §2 |
| 5 | Next has known CVEs | `npm audit` flags next@15.0.0; upgrade to 15.5.x eventually |
| 6 | docker-compose `version` attr obsolete | Harmless warning |

---

## 8. Next session — user's stated goals

1. **Fix PDF-viewing problems** (details TBD — user to specify).
2. **Design changes** (TBD — user to specify).

---

## 9. Key files reference

| Concern | Path |
|---------|------|
| Reader page | `web/app/reader/page.tsx` |
| PDF viewer | `web/components/reader/PdfViewer.tsx` |
| Chat UI | `web/components/chat/ChatPanel.tsx` |
| Notes UI | `web/components/notes/NotesPanel.tsx` |
| Coverage map | `web/components/coverage/` |
| API client | `web/lib/api-client.ts` |
| Books store | `web/lib/store.ts` |
| API proxy route | `web/app/api/proxy/[...path]/route.ts` |
| PDF proxy route | `web/app/api/pdf/route.ts` |
| Q&A backend | `api/app/routers/qa.py`, `api/app/pipeline/qa_chain.py` |
| Auth (anon) | `api/app/core/auth.py` |
| Dev scripts | `docs/dev-scripts.md` |

---

## 10. Environment facts

- Box: AWS EC2, 7.6 GB RAM, ~19 GB disk (was ~95% full; cleaned ~6 GB build cache).
- Supabase project auto-paused once (free tier) — resume in dashboard if the API 500s with `tenant/user ... not found`.
- ngrok runs **inside** the web container.
- Tools: `lsof`/`pkill` NOT available in the container; use the `/proc/*/cmdline` loop to find/kill processes.

---

## 11. Handoff — latest session

**This session: landing page (hero shelf + personal note) — committed & pushed.**

### Done
- **Accent → ink blue**: `--accent*` tokens + `FOLIO_ACCENT`. No purple left.
- **Hero shelf**: 3D book (Castiel-style) + pile of 5 mini 3D books, value-prop covers, pile→center cycle. `web/components/landing/Shelf.tsx`, `Hero.tsx`, copy in `web/content/landing.ts`.
- **Personal note section**: chaptered beats, scroll ribbon, drop cap, bookplate, signature. `web/components/landing/NoteSection.tsx`, `PersonalNote.tsx` (front-matter parser), `web/lib/fonts.ts` (Caveat), `web/content/founder-note.md` (name "sicheen").
- **Note animation** (per `docs/NOTE ANIMATION IMPLEMENTATION.md`): paper grain (`.paper`, `--scene-*` tokens, `note/PaperSurface.tsx`); 4 drawn scenes (`note/scenes/*`) with wobble filter + stroke draw-in (`pathLength`); paragraph typewriter (`note/Typewriter.tsx`, ~65 cps); handwriting via **tegaki** (`note/HandwrittenText.tsx`, margin notes + signature); **CSS highlighter** (`.highlight-mark`) — replaced rough-notation which jumped above inline text.
- **Demo (Section 3) hidden** — removed from `page.tsx`; `GuidedDemo.tsx` kept for later. Topics / How-it-works / Footer already complete.
- **Deps added**: `rough-notation`, `tegaki`, Caveat (`next/font`). Note: rough-notation now unused (highlight is CSS) — removable.
- **Docs corrected**: VoidAI/Nomic-Ollama/Gemini providers; deleted `docs/Fix.md` + `logs/errors.md`.
- **Committed + pushed**: `066206c`, `434fe66`, `7059416` ("front end design" — note animation + demo-hide).

### AI providers (authoritative)
- Generation (note gen + Q&A): **VoidAI** `gpt-oss-20b` (OpenAI-compatible, `void_acompletion()`).
- Embeddings: **Nomic via Ollama** (`nomic-embed-text`, 768-dim).
- Metadata: **Gemini** (google-genai SDK).

### Open / next
- **Containers stopped** — Supabase is resumed, but the `web`/`api` containers are down. Run `docker compose up -d web api` to test.
- **Re-test chat** — after Supabase resumes.
- **Implement notes** — scope TBD (backend + `NotesPanel.tsx` already exist; likely the AI note-generation output rendering).
- **Guided demo (Section 3)** — deferred; build later per `docs/landing-page.md`.
- **Visual pass** (agent can't screenshot): hero + note section at 390/1280px, light+dark.
- **Cerebras code cleanup** (deferred): `config.py` (`cerebras_*`), `litellm.py` (`METADATA_MODEL`), `metadata.py` docstring.
- **founder-note.md**: still Lorem Ipsum + `==phrase==` markers — real copy pending.
- Pre-existing: Sentry build fix, Better Auth, `NEXT_PUBLIC_API_URL` env override, worker OOM.

---

## 12. Handoff — the notes feature (13 units)

**Supersedes §11's "Implement notes — scope TBD": the notes feature is built.**
Design record: `docs/notes-design-notes.md`. Running log: `docs/progress-tracker.md`.

### Where it stands

- **350 tests pass**, `npx tsc --noEmit` clean, migration `0006` applied (`alembic current` → `0006`).
- Read, edit, backlinks and topic generation are each verified against the **running** stack, not only in tests.
- Containers: `web` + `api` up. Worker deliberately down.

### What a note is now

`note_session` is the note **header** (user, book, title, source, status).
`note_block` is its ordered **body** (position, kind, text, content_hash, origin).
`note_link` attaches a **citation to one block** (chunk id, section id, heading
path, page range, excerpt + hash, status `accepted | suggested | dismissed`).

Links hang off blocks, never character offsets, so editing text cannot move a
citation onto a different sentence.

Three ways to make one: **generate from a topic**, **write my own** (blank note →
editor), **paste notes** (the old session path, unchanged).

### Unit by unit

| # | Unit | Files | Gate |
|---|------|-------|------|
| 1 | `GET /notes` 500 → 200 | `services/notes.py`, `web/types/notes.ts` | 4 new tests |
| 2 | `note_block`, `note_link`, migration 0006 | `models/note_block.py`, `models/note_link.py`, migration | single head, offline DDL, applied |
| 3 | Note document service | `services/notes.py` | 12 tests |
| 4 | Create / read / autosave endpoints | `routers/notes.py`, types, client, proxy PUT+DELETE | 6 routes, tsc |
| 5 | Note view (read side) | `components/notes/NoteView.tsx` | tsc, live GET |
| 6 | Editor (write side) | `NoteEditor.tsx`, `editor/block-id.ts`, `editor/doc-blocks.ts`, `editor/BlockToolbar.tsx` | tsc, live round-trip |
| 7 | Backlinks endpoint | `services/notes.py` (`section_id` filter) | 4 tests, live |
| 8 | Backlinks in the reader | `NotesPanel.tsx`, `reader/page.tsx` | tsc, live |
| 9 | `services/retrieval.py` extracted | retrieval module + qa re-exports | 321 tests, eval unchanged |
| 10 | Topic generation pipeline | `pipeline/note_topic.py`, `pipeline/json_output.py` | 15 tests |
| 11 | `POST /notes/topic` | `services/note_topic.py`, router, types, client | **live run** |
| 12 | New-note UI | `components/notes/NewNoteSheet.tsx` | tsc, proxy 422 |
| 13 | Docs | this file, architecture, tracker, design notes | — |

### Decisions worth not re-litigating

1. **`NoteSession` stayed the header** — no parallel `Note` table.
2. **Block ids are the identity.** Autosave diffs by id; the editor's id attribute
   sets `keepOnSplit: false` because ProseMirror copies attributes on split.
3. **No automatic linking.** No `auto`/`suggested` tiers and no threshold
   calibration: no measured threshold separates in-scope from off-topic.
4. **Cards are prose** (concept / definition / explanation / `Example: …`) in one
   text column. No migration for structured cards.
5. **Nothing persists until every card validates** — no half-written notes.
6. **The server builds every excerpt and page number**; the model cites passage
   numbers only.
7. **`ON DELETE SET NULL`** on both link FKs, because re-ingestion deletes and
   recreates chunks; the stored anchor keeps a link resolvable.
8. **Explicit output budget** (`notes_topic_max_tokens = 1800`).

### Bugs this session

| Bug | Cause |
|-----|-------|
| `GET /notes` 500 for every book | `job_id` required on a schema reused for stored rows |
| Text vanished mid-paragraph | Enter splits a node and ProseMirror **copies attributes**, so both halves claimed one block id and the second write overwrote the first |
| `#` markdown never worked | The stock heading rule is `/^(#{min(levels)},level)\s$/` — with one level it required exactly three hashes |
| AI blocks became "typed" on save | `_apply_edit` overwrote `origin`, which is provenance, not state |
| Autosave returned stale blocks | `get_note_detail` needed `populate_existing` (identity map) |
| Topic generation failed live | The provider's default output cap (~1024 tokens) truncated the JSON mid-object |
| Backlinks returned 0 | Not a query bug: the citation had really been deleted by the duplicate-id bug above |

Bugs **I** introduced and repaired, on the record: `routers/notes.py` twice (a
deleted function signature, two imports merged onto one line) and
`pipeline/note_topic.py` once (merged lines) — all from malformed edit blocks,
caught by `compileall`, the route list and `tsc` rather than by reading.

### Performance work (curator-requested)

| Path | Before | After |
|------|--------|-------|
| Open Notes, warm cache | 3 requests, ~2.4 s | **0 requests** |
| Open Notes, cold | 3 requests | 1 request, 0.85 s |
| Flip pages → backlinks | 1 request per section | **0 requests** |
| Coverage map for page→section | 2.36 s, 82 KB | removed entirely |

Cause: the panel fetched the **whole coverage map** to answer "which section is
this page in". One request to this database costs 0.85–2.4 s regardless of size
(a 377-byte book row takes 2.1 s), so **request count** was the only lever. Now:
zustand + `persist` cache (`web/lib/notes-store.ts`, 30-minute TTL — the pattern
`chat-store` already used, which is why chat needed no change), `section_ids` on
each note summary so backlinks are a local filter, and the reader resolves
page→section from the book payload, which was already loading the sections and
then discarding them.

Also fixed: `list_books` and `list_note_sessions` both ran a count query that
fetched every id; they now only count when the page is full, via `func.count()`.

### New settings, keys and endpoints

- `notes_topic_max_passages = 12`, `notes_topic_max_words = 4000`,
  `notes_topic_max_tokens = 1800` in `api/app/core/config.py`.
- localStorage key `folio-notes-cache`; clearing site data resets it.
- `POST /notes/document`, `GET /notes/{id}`, `PUT /notes/{id}/blocks`,
  `POST /notes/topic`, `GET /notes?section_id=…`.
- `GET /books/{id}?load_sections=true` now returns a compact section map
  (`id`, `heading`, `page_start`, `page_end`, `level`).

### Next, in the order it will bite

1. **Block ids churn for editor-created blocks.** A split half or a new bullet has
   no id, so each save deletes the row and inserts a new one. Text is never lost,
   but a link attached to such a block would be. Fix before **manual link
   creation**: accept client-generated ids as row ids, plus an `appendTransaction`
   that stamps id-less top-level nodes.
2. **A `card` block becomes a `paragraph` once edited.**
3. **`web/` has no JS test harness** — `docToBlocks` / `blocksToContent` are the
   riskiest untested code in the repo. A `vitest` setup is roughly half an hour.
4. **No delete endpoints** for notes or links.
5. **Chapter-range generation still streams and discards its output** — pre-existing
   behaviour, untouched; it could now reuse the topic pipeline's validation and
   persistence.
6. **"Quote into notes"** (select text in the PDF → a block with an exact link) is
   built nowhere. It was the highest-value pattern from the design review and
   would make every link exact.
7. **Auth is anonymous**, so every visitor shares one set of notes. Blocking
   before any public release.

### Demo data left in the database (DDIA)

| Note | What it is |
|------|------------|
| `Live check` | the curator's typed text, 5 blocks, **no links** — its citation was destroyed by the duplicate-id bug before the fix |
| `Backlink check` | one card citing B-trees 99–103 |
| `Ss tables` | curator-created |
| `B-trees in Databases` | generated from a topic: 5 cards, 3 gaps, links on pages 90–91 and 102–103 |

### Verify it quickly

```bash
docker exec folio-api-1 python3 -m pytest -q            # 350 passed
docker exec folio-web-1 sh -c 'cd /workspace/web && npx tsc --noEmit'
docker exec folio-api-1 python3 -m evals.runner --limit 2
curl -s "localhost:8000/notes?book_id=0052b432-55e3-4945-9b5c-60e060f2b7b9&limit=5"
```

Manual path: reader → page 99–103 → Notes tab → "On this section" → open a note →
Edit → type → wait for "Saved" → Done. Then **New note → Generate from a topic**.

---

## Chat "no reply" saga (this session) — two stacked bugs

**Symptom.** Sending any question — even "hi" — showed the loading dots for a long
time and then rendered nothing. DevTools Network showed the request completing and
the body streaming in, so it was not a network failure.

### Assumptions checked and ruled out (in order)

| Assumption | How it was checked | Verdict |
|---|---|---|
| Backend erroring on `/qa` | `docker logs folio-api-1` (no traceback) + `curl -N POST /qa/{book}` | fine — streamed tokens → `done` |
| Schema/migration drift on `qa_message` | `alembic current` | fine — `0006 (head)`, nothing pending |
| Next `/api/proxy` not streaming | `curl -N POST localhost:3000/api/proxy/qa/{book}` | fine — streamed tokens |
| Client NDJSON parser broken | Node probe replicating the line-split + `JSON.parse` loop | fine — 351 events / 348 tokens |
| `folio-web-1` runs the dev server | `docker inspect folio-web-1 --format '{{.Config.Cmd}}'` | it is `[sleep infinity]` — the real dev server is `docker exec`'d inside, so its console is in the SSH terminal, not `docker logs` |

### Root cause #1 — the hang: `async start` ReadableStream producer

`web/lib/api-client.ts` built a `new ReadableStream({ async start(controller) { while (true) { … controller.enqueue(…); } } })`. The async `start` runs a producer loop that races the consumer; against a real, time-varying network body the reader can end up waiting on a stream that closes empty — spinner spins, nothing arrives.

**Evidence** (same live :3000 stream): direct read = 351 events; through the async-start wrapper = **2 events / 489 chars**; through a pull-based wrapper = 265 events. A single-chunk local mock passed (5/5) — which is why the pattern looks fine in trivial tests and only fails on real streaming.

_Note (measured later):_ a synthetic + local-`fetch` benchmark could **not** reproduce the drop, so the per-request loss is stack-specific (Next `TransformStream` proxy + undici + timing) rather than intrinsic. The hang itself was real — this fix is what made chat "faster" — and pull is still the right choice because it bounds memory and cannot race.

**Before** (both `askQuestion` and the shared `ndjson` helper):
```ts
return new ReadableStream<T>({
  async start(controller) {
    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) { /* flush buffer */ controller.close(); return; }
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";
        for (const line of lines) { /* controller.enqueue(JSON.parse(line)) */ }
      }
    } catch (e) { controller.error(e); }
  },
});
```

**After** — pull-based (one complete line per pull); `askQuestion` now reuses the helper:
```ts
return new ReadableStream<T>({
  async pull(controller) {
    while (true) {
      const nl = buffer.indexOf("\n");
      if (nl >= 0) {
        const line = buffer.slice(0, nl).trim();
        buffer = buffer.slice(nl + 1);
        if (!line) continue;
        try { controller.enqueue(JSON.parse(line) as T); return; } catch { continue; }
      }
      const { done, value } = await reader.read();
      if (done) {
        if (buffer.trim()) { try { controller.enqueue(JSON.parse(buffer) as T); } catch {} }
        controller.close();
        return;
      }
      buffer += decoder.decode(value, { stream: true });
    }
  },
});
// and in askQuestion: return this.ndjson<QaEvent>(res.body);
```
This also fixed topic-note generation — `generateTopicNotes` used the same helper.

### Root cause #2 — "displays nothing": the store wrote the wrong key

`web/lib/chat-store.ts` — `addMessage` returned the partial state correctly, but four sibling mutators returned the patch **directly**. zustand's `set(fn)` expects `fn` to return the *partial state object*; these returned the `sessions` map itself, so zustand wrote a top-level key literally named after the session id and never updated `sessions`. Result: the user bubble appeared (`addMessage` works) but the AI bubble stayed `""` forever.

**Evidence** — new `web/lib/chat-store.test.ts` failed `expected '' to be 'Hello there'`; passed after the wrap.

**Before:**
```ts
appendToken: (id, text) =>
  set((s) =>
    patchSession(s.sessions, id, (session) => { /* ... */ }),
  ),
```

**After** (same shape applied to `appendToken`, `setCitations`, `setNotCovered`, `applySummary`):
```ts
appendToken: (id, text) =>
  set((s) => ({
    sessions: patchSession(s.sessions, id, (session) => { /* ... */ }),
  })),
```

### Why it fooled us

The two bugs **stacked and masked each other**. #1 (hang) was found first and fixed → "faster now", but still blank. #2 (store key) was the actual "displays nothing". The user's hunch — *"maybe it's a state issue where we are just mutating state"* — was correct; writing a store test in isolation pinpointed it in seconds after browser debugging could not.

### Verification

- `tsc --noEmit` clean.
- `vitest`: 3 files / 25 tests pass (added `chat-store.test.ts`).
- Stream probe: pull wrapper delivers the full stream (265 events) vs async-start's 2.

### Rules to carry forward

1. Streamed NDJSON → **pull-based** `ReadableStream`; never an `async start` producer loop.
2. `set(fn)` in zustand must return the **partial state** (`{ sessions: … }`), not the nested value.
3. When a bug "got faster but is still wrong", the previous fix landed and there is a *second* bug — keep going.
4. Store logic is cheap to unit-test; do it before blaming the transport.

---

## Local-first notes sync + server delete (this session)

**Goal (curator):** notes stay a fast local cache, but are written back to the DB and imported per-user — *"calls to db are not removed but reduced."* Writes should happen when the student **finishes editing**, not on every pause.

### What was built

**Backend — one efficient request instead of many**
- `POST /notes/batch` → `upsert_notes_batch` (`api/app/services/notes.py`): one transaction, **one multi-row `INSERT … ON CONFLICT DO UPDATE` per table** (note_session / note_block / note_link), `content_hash` skip for unchanged blocks, delete-missing for removed rows, `raw_text` + `matched_section_count` computed from the payload (no extra round trips), and an **ownership guard** (a client can't overwrite another user's note). Accepts `notes` **and** `deleted` (server-side delete of owned notes with explicit child cleanup so it works with/without FK cascade).
- Dialect-aware `_upsert_insert` picks Postgres vs SQLite `ON CONFLICT` from the *session's* dialect, so tests (SQLite/aiosqlite) exercise the real path.
- The dead write path (`POST /notes/document`, `PUT /notes/{id}/blocks`, `POST /notes`) is now unused by the client but left in place.

**Frontend — client outbox + explicit flush**
- `web/lib/note-sync.ts`: notes become dirty on store change; flushed on the **editor's Done button** (`flushNoteSyncNow()`), on tab-hidden/`pagehide`, and a 60 s safety backstop. Deletes ride the flush via `pendingDeletes` (short 1.5 s debounce). One write per editing session, not one per debounce tick.
- `notes-store` gained `pendingDeletes` (append on `deleteNote`, `clearDeletes`); `sync.ts` marks imported notes synced (`markNoteSynced`) so imports aren't re-pushed.
- Cache-miss import (`syncUserData`) stays duplicate-proof: `toLocalNote` keys by server id, which now equals the local id.

**Schema cleanup (destructive — curator runs it)**
- Migration `0007_drop_note_link_columns.py` drops `note_link.chunk_id` and `note_link.distance` (the batch flow never writes them; `excerpt_hash` kept). Offline-verified: `alembic heads` = `0007`, `alembic upgrade 0006:0007 --sql` renders both `DROP COLUMN`s. **Not applied** — run `docker exec folio-api-1 python3 -m alembic upgrade head`.

**Dev visibility**
- `web/lib/request-counter.ts` counts every `/api/proxy` request; `window.__folioDbCalls` + `window.__folioReset()`, `console.debug('[folio] DB call #N …')`, and `apiClient.dbCalls`.
- `web/components/debug/db-call-badge.tsx` — a **temporary** on-screen `DB N` pill (bottom-left, tap to reset), mounted in `app/layout.tsx`. Remove the file + its two `layout.tsx` references when done.

### Design decisions
- **Flush on Done, not debounce** (curator's call). Compared state-subscription (flush when `editing→false`) vs an explicit button: the button (`NoteEditor.handleDone`) already existed, is direct, and one tap = one write; the state-watch also missed tab-switch-mid-edit. Safety net covers the non-button exits.
- **Batching over faster writes.** The DB round trip is ~1 s, so the lever is *fewer requests*, not faster SQL — hence one batch request per flush with multi-row upserts.

### Verification
- Backend: `pytest tests/services/test_note_document.py tests/services/test_notes_batch.py` → **28 passed** (incl. insert/idempotent-replay/update+drop/link-preserve/owner-guard/delete/delete-ignores-other-user).
- Frontend: `npm test` → **32 passed** (added `note-sync.test.ts`: coalesce, safety-only (no per-edit flush), on-demand, empty-guard, retry, delete, toBatchNote).
- `tsc --noEmit` clean. Migration offline-verified only.
- **Not browser-verified** (curator's dev server): confirm one edit-session = one `POST /notes/batch` via the `DB N` badge; confirm a deleted note doesn't reappear after refresh.

### Known gaps / follow-ups
- Mobile-sheet close / panel collapse **without** tapping Done doesn't flush immediately (local persist + `pagehide`/backstop cover it). Could wire the sheet's X the same way.
- Deletes are now real server deletes (curator reversed the earlier "no DELETE" decision).
- `alembic upgrade head` for `0007` still to be run by the curator.
- Debug badge + request counter are temporary; strip before shipping.

---

## Next steps (what's queued next)

The local-first notes work + the chat "no reply" fix are done. Next up, in the curator's order:

1. **Auth integration (Better Auth).** Replace the anonymous `get_current_user` fallback with real session sign-in. The per-user plumbing is already correct: every note/chat endpoint is `user_id`-scoped, and the cache-miss import (`syncUserData`) pulls *that user's* notes/chat — so once a real user id exists it "just works." Work to do: auth provider wiring (Better Auth session table already referenced in `models/qa_message.py` and `core/auth.py`), sign-in/out UI, gating `/reader`, and confirming the note/chat sync keys off the authenticated user (not the shared anonymous id).
2. **Improve chat responses.** Known levers already documented: the routing prompt (typos/abbreviations), retrieval quality (pgvector `<=>` + Nomic/Ollama embeddings), the answer prompt & grounding invariant (protected — do not weaken citations), `qa_answer_max_tokens` output cap, provider resilience (VoidAI 520/ReadTimeout retries), and the "diagrams/figures" direction still awaiting a go-ahead (approach A: pymupdf figure crop + cite; B: Gemini captions + embed; C: ColPali vision embeddings — deferred).
3. **Carry-overs:** browser-verify the note-sync + citation flows; run migration `0007`; remove the debug badge/counter; decide on dropping the now-idle `note_session.raw_text`/`status`/`matched_section_count` (kept — still written) and the dead per-note endpoints.

---

## Session — auth, chat UX, latency, and the LLM "response error" saga

### Auth (Better Auth) — live
- Better Auth wired into Next.js; `api/app/core/auth.py` validates by the `token` column and is **fail-closed** (`auth_required` default true + a production boot guard). User ids are UUIDs (`generateId → crypto.randomUUID()`, replacing nanoid). The `session`/`user`/`account`/`verification` tables live **outside Alembic** (Better Auth owns them); Supabase TLS handled in `web/lib/auth.ts`.
- Sign-in page + email verification (dev console sender), middleware gating, `/eval` email allowlist (`EVAL_ALLOWED_EMAILS`), avatar → sign-out dropdown, library avatar, 30-day sessions, `/` → `/library` redirect for signed-in users.
- **Per-user local caches** (`web/lib/user-scope.ts`): localStorage keys are namespaced `…:<userId>`, so two accounts on one browser no longer share notes/chat. Fixed the earlier "same data on both accounts" bug.

### Notes & chat UX
- Notes/chat are local-first. **Sync buttons** (notes header + chat tab bar) flush local edits then force-pull notes + chat from the server, with a 15 s cooldown — for laptop/phone parity.
- Background **"generating…" note generation** (topic + chapter) runs at module level so it survives navigation; red "don't reload" warning while generating; interrupted generations are flagged on reload; empty drafts never sync.
- Chat: assistant renders as **full-width tutor prose** (bubbles for user only), **KaTeX math + highlight.js code + GFM tables** (horizontal scroll), deliberate typewriter streaming (~166 cps, burst catch-up), 90 s stall watchdog, **resend-from-message** (truncate + regenerate) and a **Retry** on errors, and a **"thinking…" indicator** for the pre-token phase.
- **Prompt relaxed to a tutor** (teach for understanding + markdown/math/code/tables) — the `GROUNDING_SYSTEM_PROMPT` is a **protected invariant**, so this change needs the out-of-scope eval (`check_grounding.py`) before deploy.

### Latency / retrieval
- Measured truth: DB round trips ≈0.5 s because the app (us-east-1) is **cross-region** from Supabase (**ap-southeast-2**). `/books` = 6 s cold → 0.6 s warm.
- Read path: **AUTOCOMMIT** read engine, proxy session cache (60 s), auth token cache (30 s), books router TTL cache + `Cache-Control`, coverage map as a **single query**, startup DB + embedding warm-up, one shared `httpx` client.
- Retrieval: each search on **its own `AsyncSession`** + agent runs a round's searches with **`asyncio.gather`** (parallel); skip the `has_children` `EXISTS` when unused; section-index TTL cache; query-embedding **LRU**; **hybrid rerank → top 5** (`Agent._rerank`); batch-embed helper (`embed_texts`); routing `reasoning_effort:"low"`.
- Every cache is catalogued in **`docs/caching.md`**.

### Migration 0008 (written, not applied)
`CREATE INDEX ix_coverage_event_user_book_section ON coverage_event (user_id, book_id, section_id) INCLUDE (event_type)` — curator runs `docker exec folio-api-1 python3 -m alembic upgrade head`.

---

## The LLM (VoidAI) "response error" saga

- **Symptom:** some questions hung then failed — "model provider did not respond", empty answers, and nothing recorded in `/eval`.
- **Root cause (found by probing VoidAI directly):** `gpt-oss-20b` is a **reasoning model**. It spends tokens on hidden `reasoning_content` *before* any `content`. A small `max_completion_tokens` is consumed entirely by reasoning → **empty content**. The reasoning phase streams **no `content` deltas**, so the UI sees silence and it *looks* like a hang.
- **More findings:**
  - `reasoning_effort:"low"` collapses hidden thinking (measured **136 → 5** reasoning tokens, ~1.41 s → 0.88 s). Applied to the answer **and** the routing call.
  - Large prompts (~3600 words) stream fine — **not** a size limit.
  - VoidAI's **streaming** API exposes only `content`/`role` deltas — **no reasoning field** — so model reasoning **cannot** be displayed on the streaming path (the non-stream response has it). The eval therefore shows timing + error detail, not reasoning text.
- **Resilience fixes:**
  - Backend answer **read timeout 50 s** + overall **45 s** budget (checked each chunk); tighter routing timeout; client watchdog raised to **90 s** so the **server finishes and persists** the errored turn (previously the client aborted first and the turn was never saved).
  - Client `finally` clears streaming/thinking **first** and races the typewriter, so the panel can't get stuck on "thinking".
  - Failed turns now persist to `/eval` with `ttft`/`total` and the **actual provider error detail**; degenerate-loop guard + retry-before-first-token retained.
- **Root cause is provider flakiness, not our code.** Alternatives researched: **Groq** (`api.groq.com/openai/v1`, free, same `openai/gpt-oss-20b`, tools+stream) is the best drop-in; **Gemini Flash** (OpenAI-compat, free) as an independent-vendor fallback; **DeepSeek** (cheap) as tier-3. Swap = `VOID_API_BASE` / `VOID_MODEL` / `VOID_API_KEY`. A **provider fallback chain** (primary → on 5xx/timeout before first token → replay on fallback) is the real robustness fix — **deferred by curator**.

### Reranker research (current `_rerank` is a free hybrid)
- Paid/best: **Cohere Rerank 4** (~400–570 ms, ~$2/1k searches); Voyage rerank-3 close.
- Free/open: **Qwen3-Reranker-0.6B** (strongest at its size), **mxbai-rerank-v2** (fast CPU), **bge-reranker-v2-m3** (universal but ~2 s on CPU). Self-hosting needs `sentence-transformers` + torch.
- Decision pending (curator): Cohere (quick, external) vs local open model; either is a body-swap in `Agent._rerank`.

---

## Session: tables + figures ingestion, admin console, guest mode, observability, categories, PDF delivery, licensing audit

**Caches & hardening (early):** removed dead caches (`useNotesCache`, `cachedToken`, server `_CACHE`); added app-level rate limiting per user (429 + Retry-After) on AI endpoints; admin-only gating (`require_admin` by Better Auth email allow-list) on `POST /books`, `POST /books/{id}/ingest`, and status/delete; made streaming endpoints release the pooled DB connection before streaming.

**Tables (Units A–E):** parser `page.find_tables()` → GFM Markdown blocks (suppresses overlapping cell text); chunker keeps tables atomic (row-batch split, header repeat); `chunk.kind` column + migration **0009**; ingest persists `kind`, `chunk_embed_text(kind="table")` prefix; `EMBED_VERSION` 2→3; retrieval tags `kind=table` in context + citations.

**Figures (Unit F):** `pipeline/figure.py` detects all diagram types (raster image rects + clustered vector-drawing rects, table-overlap excluded, size-filtered), crops PNGs, and captions with **Gemma 4 26B** (`gemma-4-26b-a4b-it`) via google-genai under a `CaptionPacer` (30 RPM / 14.4K RPD, 429 `retryDelay` backoff). Figure chunks store **bbox + caption only** (`chunk.bbox` JSONB, migration **0010**). Ingest phase (`_ingest_figures`/`_run_figure_phase`) is idempotent + quota soft-stop; retrieval surfaces `kind=figure` + `bbox` in citations.
- **Bugs found & fixed:** `figure_max_tokens=200` returned **empty captions** (Gemma spends tokens on reasoning first) → raised to **1024**; transient `500 INTERNAL` from Gemma weren't retried → `generate_with_backoff` now retries 5xx/timeout too.

**Ingestion runner:** no Dramatiq worker (box OOMs on a 2nd Ollama) → ingestion runs **in-process** in the API via a background thread calling portable `run_ingest(book_id)` (serialized by a module lock). Startup resets stale `PROCESSING → FAILED`. CLI `ingest.py` fixed (was calling non-existent `_run_pipeline`).

**Admin console:** `/admin` hub → **`/ingest`** page: list books with status, **Start ingestion** / **Re-ingest (force)**, live progress console polling `GET /books/{id}/ingest/status` (DB-derived sections/chunks/figures/tables), **Add a book**, **Delete book**, and **category editing** (`PATCH /books/{id}`). Provenance counts come from live row counts.

**DB connections:** Supabase session-mode pooler caps **15 clients** → engine pools resized (async 5+3, sync 2+2 = 12) + `pool_pre_ping`/`pool_recycle` to stop `EMAXCONNSESSION` 500s during ingest.

**Observability:** Sentry wired (web `instrumentation.ts`/`instrumentation-client.ts` from env DSNs; API `sentry_sdk.init` from `SENTRY_DSN`). PostHog analytics (`PostHogProvider`, autocapture + manual `$pageview`). Removed the stale `tsconfig.tsbuildinfo` that was the real "Sentry build blocker". Production build must run with `NODE_ENV=production`.

**Categories:** `book.category` + migration **0011**; admin add-book + edit; library chips derived from data. Library now shows **completed books only** (not-started/processing hidden).

**PDF delivery:** in-browser viewer went through `/api/pdf` (Range proxy). Fixed inconsistent/hanging loads by **buffering small files (exact Content-Length)** / **streaming >30 MB** (no length mismatch), and not caching 206 partials. The 34 MB "just use postgres" PDF then failed in the WASM engine → added **ingest-time optimization**: PDFs over 12 MB are re-written with **Ghostscript `/ebook`** (downsample, keep text), uploaded to `optimized/<id>.pdf`, `storage_url` repointed.

**Guest mode:** unauthenticated visitors can read; **10 Q&A turns + 3 notes**, stored **client-side only** (nothing persisted). Backend `get_optional_user` lets QA stream anonymously with **no DB writes**; IP rate-limit. On login the guest bucket is discarded and the account's data (or empty) loads via user-scoped storage. Note-generation ("From a topic"/"chapter") is gated for guests.

**UX:** sonner toasts — subtle **"Sign in to save…"** on unauthorized + **"Note ready"** on note completion. driver.js **first-visit tour** on `/library` and `/reader`.

**Licensing audit (key finding):** web deps all permissive (MIT/Apache/BSD); **`@embedpdf` MIT**. But **PyMuPDF (`fitz`/`pymupdf4llm`) and Ghostscript are AGPL-3.0** → require a commercial license from Artifex (or open-sourcing the whole app) for a proprietary/SaaS product. Recommended swap: `pypdfium2` (parsing/render) + `pikepdf` (recompression). Separately: **serving copyrighted PDFs (DDIA, etc.) publicly is copyright infringement** — only host public-domain / CC-licensed / author-permitted books (SICP CC BY-SA is fine).
