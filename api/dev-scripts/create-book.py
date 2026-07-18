"""Create a Book record in the database.

Usage:
    docker compose exec api python3 /app/dev-scripts/create-book.py <title> <author> <storage_url>

Example:
    docker compose exec api python3 /app/dev-scripts/create-book.py \
        "Designing Data-Intensive Applications" \
        "Martin Kleppmann" \
        "https://jdvyoywfzvfrcckaytmm.supabase.co/storage/v1/object/public/book-pdfs/ddia.pdf"
"""

import os
import sys
import uuid

os.environ["DATABASE_URL"] = os.environ.get(
    "DATABASE_URL",
    "postgresql://postgres.jdvyoywfzvfrcckaytmm:moxbaj-Zynxu6-fugnyx@aws-1-ap-southeast-2.pooler.supabase.com:5432/postgres",
)

import sqlalchemy as sa
from sqlalchemy import create_engine


def main():
    if len(sys.argv) < 4:
        print("Usage: python3 create-book.py <title> <author> <storage_url>")
        sys.exit(1)

    title = sys.argv[1]
    author = sys.argv[2]
    storage_url = sys.argv[3]
    book_id = uuid.uuid4()

    engine = create_engine(os.environ["DATABASE_URL"])
    with engine.begin() as conn:
        conn.execute(
            sa.text(
                """
                INSERT INTO book (id, title, author, storage_url, ingestion_status, created_at, updated_at)
                VALUES (:id, :title, :author, :url, 'not_started', NOW(), NULL)
                """
            ),
            {
                "id": book_id,
                "title": title,
                "author": author,
                "url": storage_url,
            },
        )

    print(f"Book created:")
    print(f"  ID:    {book_id}")
    print(f"  Title: {title}")
    print(f"  Author: {author}")
    print("")
    print(f"Run ingestion:")
    print(f"  docker compose exec api python3 /app/dev-scripts/ingest.py {book_id} <gemini_model>")


if __name__ == "__main__":
    main()
