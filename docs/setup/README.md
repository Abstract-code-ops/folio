# Folio — Setup & Deployment Docs

Operator guides for installing, configuring, and deploying Folio.

> **About screenshots & GIF demos:** this repository ships these guides with
> **placeholder** image/GIF references (`./assets/*.png`, `./assets/*.gif`). Capture
> the real media by following each `CAPTURE` / `GIF` comment, and drop the files in
> [`./assets/`](./assets). See [`assets/README.md`](./assets/README.md) for the naming
> scheme. Product demonstration/description is intentionally **out of scope** here.

## Contents
| # | Doc | What it covers |
|---|-----|----------------|
| 1 | [Installation](./01-installation.md) | Requirements, prerequisites, first `docker compose up` |
| 2 | [Database configuration](./02-database.md) | Postgres/Supabase URLs, pooling, migrations |
| 3 | [Vector database setup](./03-vector-database.md) | pgvector, embedding dimension, `EMBED_VERSION` |
| 4 | [AI provider configuration](./04-ai-providers.md) | Ollama, VoidAI, Gemini models + keys |
| 5 | [Authentication setup](./05-authentication.md) | Better Auth, sessions, admin allow-list, guest mode |
| 6 | [Deployment](./06-deployment.md) | Production build, start, health checks, ngrok |
| 7 | [Adding books](./07-adding-books.md) | Storage upload → admin ingest → verify |

## Architecture at a glance
- **web** (`folio-web-1`, :3000) — Next.js. Browser → same-origin `/api/proxy` → API.
- **api** (`folio-api-1`, :8000) — FastAPI. Runs ingestion inline (background thread) and hosts Ollama on :11434.
- **Postgres + pgvector** — Supabase (or any Postgres with the `vector` extension).
- No separate worker container (ingestion is in-process).

![Architecture diagram](./assets/00-architecture.png)
<!-- CAPTURE: simple diagram or screenshot of `docker compose ps` showing web + api; or a 3-box architecture sketch. -->
