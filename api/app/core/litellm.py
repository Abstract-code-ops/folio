"""LiteLLM client configuration.

Provides a configured LiteLLM wrapper for embedding, generation, and
chat completions. Provider selection is configured per task type via
``settings.litellm_*_model`` — each value follows the LiteLLM provider
prefix convention (e.g. ``cerebras/llama3.1-8b``, ``gemini/gemini-2.0-flash``).

API keys are read from environment variables by LiteLLM's own key
resolution (``CEREBRAS_API_KEY``, ``GEMINI_API_KEY``, etc.) and do not
need to be passed explicitly here.
"""

from __future__ import annotations

import litellm
from litellm import aembedding, embedding

from app.core.config import settings

# ── Global LiteLLM configuration ──────────────────────────────

# Drop incomplete chunks rather than retrying — embeddings are idempotent
# and a single failure shouldn't back up the ingestion pipeline.
litellm.drop_params = True

# ── Embedding ─────────────────────────────────────────────────

EMBEDDING_MODEL: str = settings.litellm_embedding_model
EMBEDDING_DIMENSION: int = settings.litellm_embedding_dimension

# ── Generation models (for reference by other modules) ────────

METADATA_MODEL: str = settings.litellm_metadata_model
NOTE_GEN_MODEL: str = settings.litellm_note_gen_model
QA_MODEL: str = settings.litellm_qa_model


async def embed_text(text: str, model: str | None = None) -> list[float]:
    """Embed a single text string via LiteLLM and return the embedding vector.

    Args:
        text: The text to embed.
        model: LiteLLM model string. Defaults to ``EMBEDDING_MODEL``.

    Returns:
        A list of floats of length ``EMBEDDING_DIMENSION``.
    """
    model = model or EMBEDDING_MODEL
    response = await aembedding(model=model, input=text)
    return response.data[0]["embedding"]


def embed_text_sync(text: str, model: str | None = None) -> list[float]:
    """Synchronous variant of :func:`embed_text` for Dramatiq workers.

    Args:
        text: The text to embed.
        model: LiteLLM model string. Defaults to ``EMBEDDING_MODEL``.

    Returns:
        A list of floats of length ``EMBEDDING_DIMENSION``.
    """
    model = model or EMBEDDING_MODEL
    response = embedding(model=model, input=text)
    return response.data[0]["embedding"]
