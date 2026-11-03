"""One-shot diagnostic for figure captioning (run inside the api container).

Usage:
    docker exec folio-api-1 python3 /app/scripts/test_figure_caption.py [book_id]

It prints the configured caption model + token cap, sends a tiny test image to
the model, and prints the raw response text (or the exact error). If a book_id
is given, it also prints how many chunks of each kind are stored for that book
(so you can see whether figure/table chunks actually landed).
"""

from __future__ import annotations

import argparse
import base64
import os
import uuid

from app.core.config import settings

# A 1x1 transparent PNG — enough to exercise the vision path.
_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)


def test_caption() -> None:
    print("model =", settings.figure_caption_model, "| max_tokens =", settings.figure_max_tokens)
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        print("GEMINI_API_KEY is not set in this container")
        return

    from google import genai
    from google.genai import types

    client = genai.Client(api_key=key)
    try:
        response = client.models.generate_content(
            model=settings.figure_caption_model,
            contents=[
                "In one sentence, describe what this image shows.",
                types.Part.from_bytes(data=_PNG, mime_type="image/png"),
            ],
            config={
                "max_output_tokens": settings.figure_max_tokens,
                "temperature": 0.2,
            },
        )
        print("TEXT =", repr(response.text))
    except Exception as exc:  # noqa: BLE001 - we want to see the exact failure
        print("ERROR =", type(exc).__name__, str(exc)[:600])


def dump_counts(book_id: str) -> None:
    from sqlalchemy import func, select

    from app.core.db import SyncSessionLocal
    from app.models.chunk import Chunk
    from app.models.section import Section

    bid = uuid.UUID(book_id)
    with SyncSessionLocal() as db:
        rows = db.execute(
            select(Chunk.kind, func.count())
            .select_from(Chunk)
            .join(Section, Chunk.section_id == Section.id)
            .where(Section.book_id == bid)
            .group_by(Chunk.kind)
        ).all()
        print("chunks by kind:", dict(rows))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("book_id", nargs="?", default=None)
    args = parser.parse_args()

    test_caption()
    if args.book_id:
        dump_counts(args.book_id)


if __name__ == "__main__":
    main()
