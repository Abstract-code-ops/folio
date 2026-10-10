# Folio — Session Log & Handoff

_Last updated: end of this session. Read this first next session._

---

## TL;DR — current state

- **Frontend**: library + reader + coverage map + chat + notes all built and wired to the live API.
- **PDF viewer**: switched to **EmbedPDF** (`@embedpdf/react-pdf-viewer`) — working, feature-rich (highlight, search, thumbnails, scroll, page count).
- **Chat/Q&A**: fully built end-to-end but **currently broken** — the `/qa/{book_id}` endpoint returns a numpy error. **This needs fixing.**
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

- **Chat is working**: VoidAI (`gpt-oss-20b`), real token streaming, pgvector `<=>` retrieval, Nomic/Ollama embeddings, per-book persistent chat with a rolling summary + conversation history fed into the prompt.
- **Theme**: light + dark with a global toggle (default light). Tokens are CSS variables in `web/app/globals.css` (`:root` = light, `.dark` = dark).
- **Routing**: `/` = landing page, `/library` = library, `/reader` = reader. The library moved from `/` to `/library`.
- **Landing page**: static layout of all six sections done (Phase 2). The hero shelf is a first pass being rebuilt per `docs/hero-shelf.md`.
- **Decisions**: accent is **ink blue** (was purple) — three tones, see `docs/ui-context.md`; `motion` (framer-motion) approved for the landing page only.
- **To apply in code**: switch accent from purple to ink blue in `web/app/globals.css`, `web/tailwind.config.ts`, and `web/components/reader/PdfViewer.tsx` (`FOLIO_ACCENT`).
