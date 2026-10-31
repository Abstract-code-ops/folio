"""Direct provider clients. No LiteLLM.

LiteLLM was removed from this project: it is a very large dependency sitting
directly on the path of every API key, and it was pinned with an open upper
bound. We only ever used two of its features, so both are implemented here
against the providers' own HTTP APIs:

- **embeddings** — Ollama's ``/api/embed`` on the local daemon (``nomic-embed-text``);
- **chat completions** — VoidAI's OpenAI-compatible ``/chat/completions``,
  including token streaming, JSON mode and tool calling.

The return shapes intentionally mirror what the LiteLLM call sites already
expect (``response.choices[0].message.content``, ``.tool_calls``,
``part.choices[0].delta.content``), so the callers did not have to change.

Swapping a provider means changing ``void_api_base`` and the model name; nothing
here is provider-specific beyond that.
"""

from __future__ import annotations

import json
import logging
import os
import re
from types import SimpleNamespace
from typing import Any, AsyncIterator, Optional, Sequence

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

# ── Models ────────────────────────────────────────────────────

# ``litellm_embedding_model`` is stored with a provider prefix ("ollama/…"),
# which Ollama's own API does not accept.
EMBEDDING_MODEL: str = settings.litellm_embedding_model.split("/", 1)[-1]
EMBEDDING_DIMENSION: int = settings.litellm_embedding_dimension

NOTE_GEN_MODEL: str = settings.litellm_note_gen_model
QA_MODEL: str = settings.litellm_qa_model

VOID_MODEL: str = settings.void_model
VOID_API_BASE: str = settings.void_api_base

OLLAMA_API_BASE: str = os.environ.get("OLLAMA_API_BASE", "http://localhost:11434")

# Keep the embedding model resident so queries do not pay a cold model load.
_KEEP_ALIVE = os.environ.get("OLLAMA_KEEP_ALIVE", "30m")

# Embeddings are local and fast; generation can be slow, so the read timeout is
# generous — a streamed answer may pause between tokens.
_TIMEOUT = httpx.Timeout(connect=10.0, read=180.0, write=30.0, pool=10.0)

# One pooled client for every async call. Creating a client per request pays a
# fresh TLS handshake to the provider, which shows up as time-to-first-token.
_async_client: httpx.AsyncClient | None = None


def _client() -> httpx.AsyncClient:
    global _async_client
    if _async_client is None or _async_client.is_closed:
        _async_client = httpx.AsyncClient(timeout=_TIMEOUT)
    return _async_client


# ── Embeddings ────────────────────────────────────────────────


def _embed_endpoint() -> str:
    return f"{OLLAMA_API_BASE.rstrip('/')}/api/embed"


def _check_dimension(vector: list[float], model: str) -> list[float]:
    """Guard the pgvector contract: a silent dimension change corrupts columns."""
    if len(vector) != EMBEDDING_DIMENSION:
        logger.warning(
            "Embedding model %s returned %d dimensions, expected %d",
            model,
            len(vector),
            EMBEDDING_DIMENSION,
        )
    return vector


async def embed_text(text: str, model: Optional[str] = None) -> list[float]:
    """Embed one string via the local Ollama daemon."""
    target = model or EMBEDDING_MODEL
    client = _client()
    response = await client.post(
        _embed_endpoint(),
        json={"model": target, "input": text, "keep_alive": _KEEP_ALIVE},
    )
    response.raise_for_status()
    embeddings = response.json().get("embeddings") or []
    if not embeddings:
        raise RuntimeError(f"Ollama returned no embedding for model {target}")
    return _check_dimension(embeddings[0], target)


def embed_text_sync(text: str, model: Optional[str] = None) -> list[float]:
    """Blocking variant, for Dramatiq workers."""
    target = model or EMBEDDING_MODEL
    with httpx.Client(timeout=_TIMEOUT) as client:
        response = client.post(
            _embed_endpoint(),
            json={"model": target, "input": text, "keep_alive": _KEEP_ALIVE},
        )
        response.raise_for_status()
        embeddings = response.json().get("embeddings") or []
    if not embeddings:
        raise RuntimeError(f"Ollama returned no embedding for model {target}")
    return _check_dimension(embeddings[0], target)


# ── Chat completions (OpenAI-compatible) ──────────────────────


def _chat_endpoint() -> str:
    return f"{VOID_API_BASE.rstrip('/')}/chat/completions"


_TITLE_RE = re.compile(r"<title>(.*?)</title>", re.IGNORECASE | re.DOTALL)


def _error_detail(status: int, body: str) -> str:
    """One readable line for a provider failure.

    Cloudflare error pages are whole HTML documents; dumping one into the log
    buries the real signal. Keep the status and, for an error page, its title.
    """
    text = (body or "").strip()
    if text.startswith("<"):
        match = _TITLE_RE.search(text)
        summary = " ".join(match.group(1).split()) if match else "HTML error page"
    else:
        summary = " ".join(text.split()) or "no body"
    return f"provider returned {status}: {summary[:200]}"


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {os.environ.get('VOID_API_KEY', '')}",
        "Content-Type": "application/json",
    }


def _payload(
    messages: Sequence[dict[str, Any]],
    *,
    model: str,
    stream: bool,
    temperature: Optional[float],
    max_tokens: Optional[int],
    tools: Optional[Sequence[dict[str, Any]]],
    tool_choice: Optional[str],
    response_format: Optional[dict[str, Any]],
    extra: dict[str, Any],
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": model,
        "messages": list(messages),
        "stream": stream,
    }
    if temperature is not None:
        payload["temperature"] = temperature
    if max_tokens is not None:
        # VoidAI rejects `max_tokens` with an inline error chunk and accepts
        # OpenAI's newer `max_completion_tokens`. This matters beyond plumbing:
        # LiteLLM ran with `drop_params = True`, so the unsupported name was
        # dropped silently and the configured output cap never actually applied.
        payload["max_completion_tokens"] = max_tokens
    if tools:
        payload["tools"] = list(tools)
    if tool_choice:
        payload["tool_choice"] = tool_choice
    if response_format:
        payload["response_format"] = response_format
    for key, value in extra.items():
        if value is not None:
            payload[key] = value
    return payload


def _tool_call(raw: dict[str, Any]) -> SimpleNamespace:
    function = raw.get("function") or {}
    return SimpleNamespace(
        id=raw.get("id", ""),
        type=raw.get("type", "function"),
        function=SimpleNamespace(
            name=function.get("name", ""),
            arguments=function.get("arguments") or "{}",
        ),
    )


def _completion(layer: dict[str, Any]) -> SimpleNamespace:
    """Shape one non-streaming response like the LiteLLM object callers expect."""
    choice = (layer.get("choices") or [{}])[0]
    message = choice.get("message") or {}
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content=message.get("content") or "",
                    tool_calls=[
                        _tool_call(call) for call in (message.get("tool_calls") or [])
                    ]
                    or None,
                ),
                finish_reason=choice.get("finish_reason"),
            )
        ]
    )


def _delta_chunk(layer: dict[str, Any]) -> SimpleNamespace:
    """Shape one streamed chunk like ``part.choices[0].delta.content``."""
    choice = (layer.get("choices") or [{}])[0]
    delta = choice.get("delta") or {}
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                delta=SimpleNamespace(
                    content=delta.get("content"),
                    reasoning_content=delta.get("reasoning_content"),
                )
            )
        ],
        finish_reason=choice.get("finish_reason"),
    )


async def _stream(
    payload: dict[str, Any],
    timeout: httpx.Timeout,
) -> AsyncIterator[SimpleNamespace]:
    """Yield server-sent chunks. Raises if the provider reports an error inline."""
    client = _client()
    async with client.stream(
        "POST", _chat_endpoint(), json=payload, headers=_headers(), timeout=timeout
    ) as response:
        if response.status_code >= 400:
            body = await response.aread()
            raise RuntimeError(
                _error_detail(response.status_code, body.decode("utf-8", "replace"))
            )

        async for line in response.aiter_lines():
            if not line or not line.startswith("data:"):
                continue
            data = line[len("data:") :].strip()
            if not data or data == "[DONE]":
                continue
            try:
                layer = json.loads(data)
            except json.JSONDecodeError:
                continue

            # An error can arrive as a normal chunk with finish_reason
            # "error"; surface it so the caller's retry logic can act.
            choices = layer.get("choices") or [{}]
            if choices[0].get("finish_reason") == "error":
                text = ((choices[0].get("delta") or {}).get("content") or "").strip()
                raise RuntimeError(
                    f"provider aborted the stream: {text or 'no detail given'}"
                )

            yield _delta_chunk(layer)


async def void_acompletion(
    messages: Sequence[dict[str, Any]],
    *,
    model: Optional[str] = None,
    stream: bool = False,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    tools: Optional[Sequence[dict[str, Any]]] = None,
    tool_choice: Optional[str] = None,
    response_format: Optional[dict[str, Any]] = None,
    timeout: Optional[httpx.Timeout] = None,
    **extra: Any,
):
    """Call VoidAI's OpenAI-compatible chat endpoint.

    With ``stream=False`` returns an object with
    ``.choices[0].message.content`` / ``.tool_calls``.
    With ``stream=True`` returns an async iterator of chunks exposing
    ``.choices[0].delta.content``.
    """
    payload = _payload(
        messages,
        model=model or VOID_MODEL,
        stream=stream,
        temperature=temperature,
        max_tokens=max_tokens,
        tools=tools,
        tool_choice=tool_choice,
        response_format=response_format,
        extra=extra,
    )

    effective_timeout = timeout or _TIMEOUT

    if stream:
        return _stream(payload, effective_timeout)

    client = _client()
    response = await client.post(
        _chat_endpoint(), json=payload, headers=_headers(), timeout=effective_timeout
    )
    if response.status_code >= 400:
        raise RuntimeError(_error_detail(response.status_code, response.text))
    return _completion(response.json())
