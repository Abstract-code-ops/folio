"""Chunk and section embedding via LiteLLM.

Provides higher-level embedding operations over the LiteLLM client
in ``core.llm``. The low-level ``embed_text`` primitive lives in
``core.llm`` so it can be shared across pipeline modules and
worker tasks without circular imports.
"""

from __future__ import annotations

from app.core.llm import embed_text as _embed_text

# Re-export the primitive for direct use
embed_text = _embed_text
