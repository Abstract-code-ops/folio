# 4. AI provider configuration

Folio uses three providers, each for a different job. All keys go in `.env`.

| Job | Provider | Model | Env |
|-----|----------|-------|-----|
| **Embeddings** | Ollama (local, in api container :11434) | `nomic-embed-text` (768-dim) | `OLLAMA_API_BASE`, `OLLAMA_KEEP_ALIVE` |
| **Answer generation / Q&A** | VoidAI (OpenAI-compatible) | `gpt-oss-20b` | `VOID_API_KEY`, `VOID_API_BASE`, `VOID_MODEL` |
| **Section metadata** | Google Gemini | `gemini-3.1-flash-lite` | `GEMINI_API_KEY` |
| **Figure captions** | Google Gemini (vision) | `gemma-4-26b-a4b-it` | `GEMINI_API_KEY` |

```dotenv
GEMINI_API_KEY=<key>
VOID_API_KEY=<key>
# optional overrides:
# VOID_API_BASE=https://api.voidai.app/v1
# VOID_MODEL=gpt-oss-20b
```

## Ollama (embeddings)
Runs inside the `api` container (installed in `Dockerfile.dev`); the web/api talk to
`http://localhost:11434`. The model pulls on first use. Keep it warm with
`OLLAMA_KEEP_ALIVE`.

**Do not start a second worker container** — a second Ollama OOMs a small box. Ingestion
runs in the API process for this reason.

![Ollama embedding model](./assets/04-ollama.png)
<!-- CAPTURE: `docker exec folio-api-1 ollama list` showing nomic-embed-text, OR the api startup log line "embedding warm". -->

## Generation / Q&A (VoidAI)
`gpt-oss-20b` is a **reasoning** model: a low token budget is consumed by hidden
reasoning → empty answers. Folio sets `reasoning_effort:"low"` and uses generous timeouts.
Swap providers by changing `VOID_API_BASE` / `VOID_MODEL` / `VOID_API_KEY` (Groq / Gemini
Flash are drop-ins). See `docs/session-log.md` for the full saga.

## Metadata + figure captions (Gemini)
- Section metadata uses `gemini_metadata_model` (`gemini-3.1-flash-lite`).
- Figure captions use `figure_caption_model` (`gemma-4-26b-a4b-it`) with
  **`figure_max_tokens=1024`** — below ~1000 the model returns **empty** captions (it
  spends tokens on reasoning first). Paced to the free tier (30 RPM / 14.4K RPD) with
  429/5xx backoff.

GIF: figure captioning in action
![Figure captioning demo](./assets/04-figure-captioning.gif)
<!-- GIF (10–15s): run ingest on a book with images; show `[PIPELINE] Detected N figure region(s)` → `Captioned M figure(s)`. -->

## Verify each provider
```bash
# Ollama embeddings
docker exec folio-api-1 python3 -c "import asyncio; from app.core.llm import embed_text; print(len(asyncio.run(embed_text('hello'))))"   # → 768

# Gemini (metadata + vision)
docker exec folio-api-1 python3 /app/scripts/test_figure_caption.py
```

## Next
→ [5. Authentication setup](./05-authentication.md)
