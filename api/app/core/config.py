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
    # Embedding → Nomic via local Ollama.
    # Generation / Q&A → VoidAI (OpenAI-compatible). Metadata → Gemini.
    litellm_embedding_model: str = "ollama/nomic-embed-text"
    litellm_embedding_dimension: int = 768
    # Metadata extraction uses Gemini as primary, Cerebras as fallback.
    gemini_metadata_model: str = "gemini-2.0-flash"  # google-genai SDK uses bare model name, not LiteLLM's "gemini/..." prefix
    cerebras_metadata_model: str = "cerebras/gemma-4-31b"
    # Legacy alias — kept for backward compat; now maps to cerebras_metadata_model.
    litellm_metadata_model: str = "cerebras/gemma-4-31b"
    # General metadata model string (used by litellm.py METADATA_MODEL reference).
    # Note: metadata.py no longer reads this directly — see gemini_metadata_model / cerebras_metadata_model.
    litellm_note_gen_model: str = "gpt-oss-20b"
    litellm_qa_model: str = "gpt-oss-20b"

    # ── VoidAI (OpenAI-compatible) — generation provider ──────
    void_api_base: str = "https://api.voidai.app/v1"
    void_model: str = "gpt-oss-20b"

    # ── Metadata extraction retry config ──────────────────────
    # Gemini retry: fixed backoff for RateLimitError.
    gemini_max_retries: int = 3
    gemini_retry_wait_seconds: int = 120
    # Cerebras retry: exponential backoff.
    cerebras_max_retries: int = 5
    cerebras_retry_min_wait: int = 10
    cerebras_retry_max_wait: int = 90

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
