"""FastAPI app entry point."""

import os

from fastapi import FastAPI

from app.core.config import enforce_auth_config, settings
from app.routers import books, coverage, notes, qa

# Fail closed: refuse to boot if authentication is disabled in production.
enforce_auth_config()

app = FastAPI(title="Folio API", version="0.1.0")

# ── Sentry (error tracking) ────────────────────────────────────
# DSN comes from the environment (SENTRY_DSN). No-op when unset, so dev/test
# without a DSN still runs.
_sentry_dsn = os.environ.get("SENTRY_DSN")
if _sentry_dsn:
    try:
        import sentry_sdk

        sentry_sdk.init(
            dsn=_sentry_dsn,
            traces_sample_rate=0.1,
            environment=os.environ.get("ENV") or settings.environment,
        )
    except Exception:  # never let observability break startup
        pass


@app.on_event("startup")
async def _warm_db_pool() -> None:
    """Open a pooled DB connection at boot.

    The first request to Supabase otherwise pays the TLS handshake — measured
    ~6s cold vs ~0.6s warm. Warming one connection here removes that hit from
    the user's first page load.
    """
    from sqlalchemy import text

    from app.core.db import async_engine

    try:
        async with async_engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:  # never let warm-up failure block startup
        pass

    # Keep the embedding model warm too (see OLLAMA_KEEP_ALIVE).
    try:
        from app.core.llm import embed_text

        await embed_text("warmup")
    except Exception:  # best-effort; Ollama may not be up yet
        pass

    # Inline ingestion runs in this process, so a fresh start has no in-flight
    # ingest: any book left PROCESSING from a previous run is stale. (Only valid
    # while ingestion is inline; a dedicated ingest server owns this later.)
    try:
        from sqlalchemy import update

        from app.core.db import AsyncSessionLocal
        from app.models.book import Book, IngestionStatus

        async with AsyncSessionLocal() as session:
            await session.execute(
                update(Book)
                .where(Book.ingestion_status == IngestionStatus.PROCESSING)
                .values(ingestion_status=IngestionStatus.FAILED)
            )
            await session.commit()
    except Exception:  # best-effort; never block startup
        pass

    # Silence MuPDF's C-level chatter. Some PDFs (ebook rips) have malformed
    # objects and PyMuPDF prints "MuPDF error: format error: object is not a
    # stream" to stderr while still rendering fine. These flags are
    # process-global, so this covers parsing and the inline figure phase.
    try:
        import fitz  # PyMuPDF

        fitz.TOOLS.mupdf_display_errors(False)
        fitz.TOOLS.mupdf_display_warnings(False)
    except Exception:  # best-effort
        pass


app.include_router(books.router)
app.include_router(coverage.router)
app.include_router(notes.router)
app.include_router(qa.router)
