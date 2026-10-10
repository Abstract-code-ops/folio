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
from litellm import acompletion, aembedding, embedding

from app.core.config import settings

# ── Global LiteLLM configuration ──────────────────────────────

# Drop incomplete chunks rather than retrying — embeddings are idempotent
# and a single failure shouldn't back up the ingestion pipeline.
litellm.drop_params = True

# Tell LiteLLM where to find the local Ollama server.
# Defaults to http://localhost:11434 — can be overridden via env var.
import os
os.environ.setdefault("OLLAMA_API_BASE", "http://localhost:11434")

# ── Embedding ─────────────────────────────────────────────────

EMBEDDING_MODEL: str = settings.litellm_embedding_model
EMBEDDING_DIMENSION: int = settings.litellm_embedding_dimension

# ── Generation models (for reference by other modules) ────────

METADATA_MODEL: str = settings.cerebras_metadata_model
NOTE_GEN_MODEL: str = settings.litellm_note_gen_model
QA_MODEL: str = settings.litellm_qa_model

# ── VoidAI (OpenAI-compatible generation provider) ────────────

VOID_MODEL: str = settings.void_model
VOID_API_BASE: str = settings.void_api_base


async def void_acompletion(
    messages: list[dict[str, str]],
    *,
    model: str | None = None,
    stream: bool = False,
    temperature: float = 0.2,
    **kwargs,
):
    """Call VoidAI (OpenAI-compatible) via LiteLLM's OpenAI provider.

    Routes ``openai/<model>`` through ``VOID_API_BASE`` using
    ``VOID_API_KEY``. Returns the completion, or an async stream iterator
    when ``stream=True``.
    """
    model = model or VOID_MODEL
    return await acompletion(
        model=f"openai/{model}",
        messages=messages,
        api_base=VOID_API_BASE,
        api_key=os.environ.get("VOID_API_KEY", ""),
        stream=stream,
        temperature=temperature,
        **kwargs,
    )


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
