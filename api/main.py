"""FastAPI app entry point."""

from fastapi import FastAPI

from app.core.config import enforce_auth_config
from app.routers import books, coverage, notes, qa

# Fail closed: refuse to boot if authentication is disabled in production.
enforce_auth_config()

app = FastAPI(title="Folio API", version="0.1.0")


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


app.include_router(books.router)
app.include_router(coverage.router)
app.include_router(notes.router)
app.include_router(qa.router)

