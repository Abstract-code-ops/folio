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
    # Column that holds the session token. Better Auth stores the session
    # cookie/token in a dedicated column (default name ``token``), distinct
    # from the row ``id``. Requests are looked up by this column, not by id.
    better_auth_session_token_column: str = "token"
    # Deployment environment. "production" arms the fail-closed auth guard in
    # ``enforce_auth_config`` below (also honours the ``ENV`` env var).
    environment: str = "development"
    # Require a valid session token on every protected request. Defaults to
    # True — auth fails closed. Set False only for local development; the app
    # refuses to start with this False when the environment is production.
    auth_required: bool = True

    # ── AI Providers (LiteLLM) ────────────────────────────────
    # Embedding → Nomic via local Ollama.
    # Generation / Q&A → VoidAI (OpenAI-compatible). Metadata → Gemini.
    litellm_embedding_model: str = "ollama/nomic-embed-text"
    litellm_embedding_dimension: int = 768
    # Metadata extraction uses Gemini (google-genai SDK, bare model name - no
    # "models/" or "gemini/" prefix).
    # gemini-2.0-flash is no longer served by the API: models.list() returns no
    # 2.0 models at all (checked 2026-10-17), so metadata extraction was failing
    # on a retired model name.
    gemini_metadata_model: str = "gemini-3.1-flash-lite"
    litellm_note_gen_model: str = "gpt-oss-20b"
    litellm_qa_model: str = "gpt-oss-20b"

    # ── VoidAI (OpenAI-compatible) — generation provider ──────
    void_api_base: str = "https://api.voidai.app/v1"
    void_model: str = "gpt-oss-20b"

    # ── Metadata extraction retry config ──────────────────────
    # Gemini retry: fixed backoff for RateLimitError.
    gemini_max_retries: int = 3
    gemini_retry_wait_seconds: int = 120
    # Batch sizing. A batch of 20 sections asked the model for more JSON than
    # the output cap allows, so late sections in a batch came back empty and
    # the whole batch was silently discarded. Six per call is the safe default.
    gemini_metadata_batch_size: int = 6
    gemini_metadata_max_output_tokens: int = 4096
    # Extra passes that re-request sections which came back unanswered.
    gemini_metadata_repair_attempts: int = 2
    # Delay between batches, for rate-limit headroom.
    gemini_batch_delay_seconds: int = 70

    # ── Chunking ──────────────────────────────────────────────
    # Target maximum chunk size in words. 750 stays the default until the eval
    # says otherwise; smaller sizes are an experiment for U8, not an assumption.
    chunk_max_words: int = 750
    # Blocks to repeat at the start of the next chunk. Off by default: overlap
    # costs tokens on every query and has not been measured yet.
    chunk_overlap_blocks: int = 0

    # ── Retrieval v2 (U8) ─────────────────────────────────────
    # Query-side nomic prefix. Off until every book is at embed_version 2; when
    # on, retrieval is restricted to that version so documents and queries are
    # never compared across different embedding spaces.
    embed_prefixes_enabled: bool = False
    # Drop hits whose cosine distance exceeds this. None disables the filter;
    # set it only from the measured in-scope and out-of-scope distributions.
    retrieval_max_distance: float | None = None
    # Keep only each section's best chunk, so one section cannot fill the
    # context with near-duplicate passages.
    retrieval_dedup_sections: bool = True
    # Exclude connective stubs: short, childless, and with no definitions,
    # equations or examples in metadata.
    retrieval_exclude_connective: bool = False
    # Candidates fetched per requested result, to absorb filtering and dedup.
    retrieval_overfetch: int = 3
    # Chunks retrieved per question. Holding this fixed while shrinking chunks
    # trades recall for a smaller prompt; raising it holds the word budget
    # instead, which is the fair way to compare chunk sizes.
    retrieval_top_k: int = 5

    # ── Topic notes ───────────────────────────────────────────
    # Passages handed to the topic generator. Both bounds exist because they
    # measure different things: the count caps the prompt's structure, the word
    # budget caps its cost. At the default chunk size the word budget binds
    # first, which is the intended behaviour.
    notes_topic_max_passages: int = 12
    notes_topic_max_words: int = 4000
    # Output budget. The provider's default cap truncates a full set of cards
    # mid-JSON, which surfaces as a parse failure rather than a short answer.
    notes_topic_max_tokens: int = 1800
    # Add the previous and next chunk of each matched section, marked as
    # context. Off by default: it only adds prompt cost, and a retrieval-only
    # harness cannot show the answer-quality benefit.
    retrieval_expand_neighbours: bool = False
    # Add the parent section's summary, marked as context. Off by default for
    # the same reason.
    retrieval_parent_context: bool = False
    # Add the previous and next chunk of each matched section, marked as
    # context. Off by default: a retrieval-only harness can measure the prompt
    # cost but not the answer-quality benefit.
    retrieval_expand_neighbours: bool = False
    # Add the parent section's summary, marked as context. Off by default for
    # the same reason.
    retrieval_parent_context: bool = False

    # ── Q&A answer generation ─────────────────────────────────
    # Hard cap on generated answer length. The prompt asks for 2-4 paragraphs,
    # so this bounds a runaway model: gpt-oss-20b has been observed degenerating
    # into a single repeated token until the provider killed the stream.
    qa_answer_max_tokens: int = 1000

    # Cap the answer call's read timeout (seconds) BELOW the client's 60s
    # watchdog, so a hung provider ends the stream server-side and the turn is
    # still persisted (as an error) for the eval, instead of lingering for the
    # provider's full 180s and never being recorded.
    qa_answer_read_timeout: float = 50.0

    # Overall budget for generating one answer. Checked each streamed chunk, so a
    # provider that keeps dribbling empty/reasoning deltas (never a content token)
    # is cut off here rather than hanging. Kept below the routing timeout + client
    # watchdog so the turn still ends server-side and is persisted for the eval.
    qa_answer_total_timeout: float = 45.0

    # gpt-oss-20b is a *reasoning* model: it spends tokens on hidden reasoning
    # before any answer text (measured 136 reasoning tokens at default vs 5 at
    # "low"), which delays the first token and can consume the whole output
    # budget so the answer comes back empty. "low" keeps answers fast and whole.
    qa_reasoning_effort: str = "low"

    # ── Q&A prompt dump (review aid) ──────────────────────────
    # Write the exact messages sent to the answer model (system + history +
    # context) to a markdown file so the prompt can be reviewed. Overwritten
    # on each grounded turn. Disable in production.
    qa_prompt_dump: bool = True
    qa_prompt_dump_path: str = "logs/qa-prompt.md"

    # ── Q&A agent (U11, revised) ──────────────────────────────
    # The agent decides whether a message needs the book at all: greetings and
    # off-topic messages are answered without retrieval, so they produce no
    # citations and no coverage events. Set False to fall back to the
    # always-retrieve grounded path.
    qa_agent_enabled: bool = True
    # Model for the routing decision. One string here switches models; it goes
    # through void_acompletion, so switching *provider* also means changing
    # void_api_base above.
    qa_agent_model: str = "gpt-oss-20b"
    # How many searches the agent may make before it must answer. Each search
    # costs one embedding and adds context to the final prompt.
    qa_agent_max_searches: int = 2
    # Routing is a classification step: keep it deterministic.
    qa_agent_temperature: float = 0.0

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


def enforce_auth_config() -> None:
    """Refuse to run with authentication disabled in production.

    Called at import time from ``main.py``. The whole point is to fail closed:
    a ``auth_required=False`` deployment is a development convenience, and it
    must never reach production silently.
    """
    import os

    environment = (os.getenv("ENV") or settings.environment or "").strip().lower()
    if environment == "production" and not settings.auth_required:
        raise RuntimeError(
            "Refusing to start: auth_required is False while the environment is "
            "'production'. Authentication must stay enabled in production."
        )
