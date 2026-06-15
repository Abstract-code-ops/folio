"""Environment config and settings.

All environment-specific configuration — API keys, secrets, database URLs,
LiteLLM provider config, point value thresholds — is read from environment
variables. Nothing is hardcoded.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ── Database ──────────────────────────────────────────────
    # Sync DSN — used by Alembic and Dramatiq workers (psycopg2).
    database_url: str = "postgresql://folio:folio@localhost:5432/folio"

    # Async DSN — used by FastAPI runtime (asyncpg).
    # Must use postgresql+asyncpg:// scheme.
    database_url_async: str = "postgresql+asyncpg://folio:folio@localhost:5432/folio"

    # ── Supabase ──────────────────────────────────────────────
    supabase_url: str = ""
    supabase_key: str = ""
    supabase_storage_bucket: str = "book-pdfs"

    # ── Auth (Better Auth session table) ──────────────────────
    better_auth_session_table: str = "session"

    # ── AI Providers (LiteLLM) ────────────────────────────────
    litellm_embedding_model: str = "text-embedding-ada-002"
    litellm_embedding_dimension: int = 1536
    litellm_metadata_model: str = "gemini/gemini-2.0-flash"
    litellm_note_gen_model: str = "gemini/gemini-2.0-flash"
    litellm_qa_model: str = "gemini/gemini-2.0-flash"

    # ── Coverage scoring thresholds ───────────────────────────
    coverage_points_page_viewed: int = 1
    coverage_points_note_matched: int = 3
    coverage_points_notes_generated: int = 4
    coverage_points_qa_asked: int = 5
    coverage_points_quiz_answered: int = 5
    coverage_score_cap: int = 15

    # Connective section word-count threshold
    connective_word_count_threshold: int = 150

    model_config = {"env_prefix": "", "case_sensitive": False}


settings = Settings()
