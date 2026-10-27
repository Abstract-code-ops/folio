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
