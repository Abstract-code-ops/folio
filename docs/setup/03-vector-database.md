# 3. Vector database setup

Folio does **not** run a separate vector database. Vectors live in the **same Postgres**
via the [`pgvector`](https://github.com/pgvector/pgvector) extension, and similarity
search uses pgvector's cosine operator.

## How it's set up (already in migrations)
- Migration **0001** runs `CREATE EXTENSION IF NOT EXISTS vector`.
- **0002** set the embedding dimension to **768** (switch from 1536-dim ada-002 to
  **nomic-embed-text** via Ollama).
- Columns: `section.embedding vector(768)` and `chunk.embedding vector(768)`.
- Retrieval orders by cosine distance (`embedding <=> :query`) and filters by
  `embed_version`.

```bash
# confirm the extension exists
docker exec folio-api-1 python3 -c "import asyncio; from app.core.db import async_engine; from sqlalchemy import text
async def m():
    async with async_engine.connect() as c:
        print((await c.execute(text(\"select extname from pg_extension where extname='vector'\")).scalar()))
asyncio.run(m())"
# → vector
```

![pgvector extension](./assets/03-pgvector-extension.png)
<!-- CAPTURE: terminal output of the query above showing `vector`, OR Supabase → Database → Extensions with `vector` enabled. -->

## Requirement
Your Postgres must allow `CREATE EXTENSION vector`. Supabase has pgvector available;
self-hosted needs the `pgvector` package installed on the Postgres image.

## Embeddings & versions
- Embeddings are produced **at ingest time** by Ollama's `nomic-embed-text` (768-dim).
- `EMBED_VERSION` (in `app/pipeline/embed_inputs.py`) tags every embedding; bumping it
  (e.g. `2 → 3` for typed table/figure chunks) forces a re-ingest to upgrade old rows.
- Re-embed without re-parsing: `app/workers/reembed.py` (`reembed_book`).

GIF: ingest → vectors
![Vector ingest demo](./assets/03-vector-ingest.gif)
<!-- GIF (8–12s): run ingest, then show `chunks by kind:` + a psql/Supabase row with a non-null embedding, or the library Q&A returning an answer. -->

## Next
→ [4. AI provider configuration](./04-ai-providers.md)
