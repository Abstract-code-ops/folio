"""Embedding input strings for nomic-embed-text (plan units U7 and U8).

nomic-embed-text is trained with task prefixes: a passage is embedded with
``search_document:`` and a question with ``search_query:``. Embedding documents
without the prefix (which is what v1 ingest did) throws that signal away, and it
also embedded chunks with no heading context at all, so a generic question
matched chapter prose rather than the subsection.

The two sides are a **matched pair**. Prefixing documents without prefixing
queries is not an improvement, it is a mismatch, which is why the query side is
behind ``settings.embed_prefixes_enabled`` and only turns on once every book is
at ``EMBED_VERSION``.

Ingest, the re-embed job and the retrieval path all call these functions, so the
strings cannot drift between them.
"""

from __future__ import annotations

from typing import Sequence

DOCUMENT_PREFIX = "search_document:"

# Query-side prefix. Only used when ``settings.embed_prefixes_enabled`` is on,
# which requires every book to be at EMBED_VERSION.
QUERY_PREFIX = "search_query:"

# Query-side prefix, used only when settings.embed_prefixes_enabled is on.
QUERY_PREFIX = "search_query:"

# 1 = embeddings built without task prefixes (pre-U7). 2 = nomic prefix inputs.
# Lives here so ingest, re-embed and retrieval cannot disagree, and so the
# re-embed module does not have to import the ingest module.
EMBED_VERSION = 2

# Ancestor headings are joined with this separator to form a breadcrumb.
BREADCRUMB_SEPARATOR = " > "

# How much of the section's opening text to include beside its summary.
SECTION_OPENING_WORDS = 300


def build_breadcrumb(headings: Sequence[str]) -> str:
    """Join a heading path (ancestors first, then the section itself)."""
    parts = [heading.strip() for heading in headings if heading and heading.strip()]
    return BREADCRUMB_SEPARATOR.join(parts)


def query_embed_text(question: str, *, prefixed: bool) -> str:
    """Input for a search query.

    nomic expects ``search_query:`` on the question side to match the
    ``search_document:`` prefix on passages. Prefixing one side without the
    other puts them in different spaces, which is worse than prefixing neither.
    """
    text = (question or "").strip()
    if not prefixed:
        return text
    return f"{QUERY_PREFIX} {text}"


def chunk_embed_text(breadcrumb: str, content: str) -> str:
    """Input for a chunk: ``search_document: {breadcrumb}\\n{content}``.

    The stored ``content`` stays clean -- the prefix and breadcrumb exist only
    in the string handed to the embedder, never in what is saved or shown.
    """
    body = f"{breadcrumb}\n{content}" if breadcrumb else content
    return f"{DOCUMENT_PREFIX} {body}"


def section_embed_text(
    *,
    breadcrumb: str,
    summary: str,
    concepts: Sequence[str],
    raw_text: str,
) -> str:
    """Input for a section: breadcrumb, summary, concepts, opening text.

    Falls back to the breadcrumb plus the opening text when the metadata has no
    summary (front matter, or a section the metadata pass could not summarise).
    Nothing is invented: an absent summary simply contributes nothing.
    """
    opening = " ".join(raw_text.split()[:SECTION_OPENING_WORDS])

    parts: list[str] = []
    if breadcrumb:
        parts.append(breadcrumb)

    clean_summary = (summary or "").strip()
    if clean_summary:
        parts.append(clean_summary)
        clean_concepts = [c.strip() for c in concepts if c and c.strip()]
        if clean_concepts:
            parts.append("Concepts: " + ", ".join(clean_concepts))

    if opening:
        parts.append(opening)

    return f"{DOCUMENT_PREFIX} " + "\n".join(parts) if parts else DOCUMENT_PREFIX
