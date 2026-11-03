"""Check every book's storage_url is reachable (run in the api container).

Usage:
    docker exec folio-api-1 python3 /app/scripts/check_book_urls.py

Prints an HTTP status + content-type + size for each book's PDF URL. If the
non-ddia books show 404/403/HTML, their storage_url points at a file that isn't
there (a data problem — re-upload / fix the URL). If they all show 200 with
application/pdf, the viewer/proxy is the problem, not the file.
"""

from __future__ import annotations

import asyncio

import httpx
from sqlalchemy import select

from app.core.db import SyncSessionLocal
from app.models.book import Book


async def main() -> None:
    with SyncSessionLocal() as db:
        books = list(db.scalars(select(Book).order_by(Book.title.asc())))

    print(f"{len(books)} books\n")
    async with httpx.AsyncClient(follow_redirects=True, timeout=25) as client:
        for book in books:
            url = book.storage_url
            try:
                resp = await client.head(url)
                # Some storages disallow HEAD — fall back to a 1-byte GET.
                if resp.status_code in (403, 405) or resp.status_code >= 500:
                    resp = await client.get(url, headers={"Range": "bytes=0-1023"})
                ct = resp.headers.get("content-type", "?")
                cl = resp.headers.get("content-length", "?")
                flag = "OK " if resp.status_code in (200, 206) and "pdf" in ct.lower() else "!! "
                print(f"{flag}{resp.status_code:>4}  {ct:<24} {cl:>12}  {book.ingestion_status.value:<11} {book.title[:38]}")
            except Exception as exc:  # noqa: BLE001
                print(f"!! ERR  {type(exc).__name__}: {str(exc)[:60]}  {book.title[:38]}")
            print(f"     {url}")


if __name__ == "__main__":
    asyncio.run(main())
