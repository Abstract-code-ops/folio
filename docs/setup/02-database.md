# 2. Database configuration

Folio uses **PostgreSQL**. Supabase is the reference deployment (Postgres + pgvector + Storage in one project), but any Postgres 15+ with the `vector` extension works.

## Connection strings
Two are required (see [`app/core/config.py`](../../api/app/core/config.py)):
| Var | Driver | Used by |
|-----|--------|---------|
| `DATABASE_URL` | `psycopg2` (sync) | Alembic migrations, inline ingestion (`SyncSessionLocal`) |
| `DATABASE_URL_ASYNC` | `asyncpg` (`postgresql+asyncpg://`) | FastAPI request path |

```dotenv
DATABASE_URL=postgresql://USER:PASS@aws-1-<region>.pooler.supabase.com:5432/postgres
DATABASE_URL_ASYNC=postgresql+asyncpg://USER:PASS@aws-1-<region>.pooler.supabase.com:5432/postgres
```

## ⚠️ Supabase pooler = 15-client cap (session mode)
The session-mode pooler caps **total clients at 15**. Folio's pools are sized to fit
(`api/app/core/db.py`: async `5+3`, sync `2+2` = 12) — **don't raise them** without a
larger plan or the transaction-mode pooler, or you'll hit `EMAXCONNSESSION` 500s during
ingest.

![Supabase connection pool](./assets/02-supabase-pooler.png)
<!-- CAPTURE: Supabase dashboard → Database → connection pooling settings (or a screenshot of db.py pool sizing). -->

## Migrations (schema)
The schema is managed with **Alembic**. Always run it *inside the api container*; the
curator owns the database (never apply DDL from a laptop).

```bash
# check current revision (single head expected)
docker exec folio-api-1 python3 -m alembic current
docker exec folio-api-1 python3 -m alembic heads

# apply everything
docker exec folio-api-1 python3 -m alembic upgrade head
```
Current head: **0011** (`0011_book_category`). Migrations `0009` (`chunk.kind`) and
`0010` (`chunk.bbox`) are required for the tables/figures features.

GIF: running migrations
![Migrations demo](./assets/02-migrations.gif)
<!-- GIF (6–10s): `alembic current` (behind) → `alembic upgrade head` → `alembic current` (0011). -->

## Verify
```bash
docker exec folio-api-1 python3 -c "import asyncio; from app.core.db import async_engine; from sqlalchemy import text; \
asyncio.run((lambda: None)() )" 2>/dev/null || true
curl -s http://localhost:8000/books        # 200, JSON list
```

## Next
→ [3. Vector database setup](./03-vector-database.md)
