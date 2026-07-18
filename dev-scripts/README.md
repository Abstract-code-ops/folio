# Dev Scripts — CLI tasks for Folio

All scripts run inside the API container via `docker compose exec api`.
Scripts live in `api/dev-scripts/` and are accessible at `/app/dev-scripts/` inside
the container.

---

## Start the dev server

```bash
# Run from project root
npx next dev --port 3001
```

Starts the Next.js dev server on port 3001 with live reload.
Open http://localhost:3001 in a browser (or use ngrok to access from phone).

---

## Expose dev server to phone (ngrok)

```bash
# One-time setup (already done — token is in .env)
ngrok config add-authtoken <token>

# Start tunnel
ngrok http 3001 --log=stdout
```

Opens a public URL like `https://xxx.ngrok-free.dev`. Open that URL on your phone
to see the live UI. Changes to the code reload automatically.

---
Scripts live in `api/dev-scripts/` and are accessible at `/app/dev-scripts/` inside the container.

---

## `upload-book.sh` — Download a PDF and upload it to Supabase Storage

```bash
./api/dev-scripts/upload-book.sh <url> [filename]
```

Uploads a PDF from any URL to the `book-pdfs` Supabase Storage bucket.
**Runs from the host** (not inside the container).

**Examples:**

```bash
./api/dev-scripts/upload-book.sh https://web.mit.edu/6.001/6.037/sicp.pdf sicp.pdf
```

**Output:** prints the public URL to use when creating the Book record.

---

## `create-book.py` — Create a Book record in the database

```bash
docker compose exec api python3 /app/dev-scripts/create-book.py <title> <author> <storage_url>
```

Creates a `Book` row with `ingestion_status = not_started`. Prints the new book's UUID.

**Examples:**

```bash
docker compose exec api python3 /app/dev-scripts/create-book.py \
  "Designing Data-Intensive Applications" \
  "Martin Kleppmann" \
  "https://jdvyoywfzvfrcckaytmm.supabase.co/storage/v1/object/public/book-pdfs/ddia.pdf"
```

---

## `ingest.py` — Full book ingestion pipeline

```bash
docker compose exec api python3 /app/dev-scripts/ingest.py <book_id> <gemini_model>
```

Runs the full ingestion: parse PDF (with OCR) → chunk → embed (Ollama/nomic) → metadata extraction (Gemini) → persist to DB.

**Early-stop guard:** If the PDF yields < 100 total words of extractable text (even after OCR), the script prints a clear error and exits immediately — no partial DB writes.

**Examples:**

```bash
docker compose exec api python3 /app/dev-scripts/ingest.py 62e581b4-9d31-4422-9100-7b6be671323d gemini-2.5-flash-lite
```

---

## `fill-metadata.py` — Fill missing section metadata

```bash
docker compose exec api python3 /app/dev-scripts/fill-metadata.py <book_id> [batch_size] [--model model_name]
```

Finds sections with empty/null metadata and runs batch extraction via Gemini. Useful when the initial ingestion ran but Gemini quota was exhausted.

**Examples:**

```bash
docker compose exec api python3 /app/dev-scripts/fill-metadata.py 62e581b4-9d31-4422-9100-7b6be671323d 10 --model gemini-2.5-flash-lite
```

---

## `check-quota.py` — Check Gemini API quota

```bash
docker compose exec api python3 /app/dev-scripts/check-quota.py [model_name]
```

Makes a minimal test call to Gemini to verify the API key has quota remaining.

**Exit codes:** 0 = available, 1 = rate-limited / exhausted, 2 = other error.

**Examples:**

```bash
docker compose exec api python3 /app/dev-scripts/check-quota.py gemini-2.5-flash-lite
```

---

## Full workflow for a new book

```bash
# 1. Upload PDF (run from host)
BOOK_URL=$(./api/dev-scripts/upload-book.sh https://example.com/book.pdf my-book.pdf)

# 2. Create Book record
BOOK_ID=$(docker compose exec api python3 /app/dev-scripts/create-book.py "Title" "Author" "$BOOK_URL")

# 3. Check Gemini quota
docker compose exec api python3 /app/dev-scripts/check-quota.py

# 4. Run ingestion
docker compose exec api python3 /app/dev-scripts/ingest.py "$BOOK_ID" gemini-2.5-flash-lite

# 5. (If quota was exhausted) Fill metadata later
docker compose exec api python3 /app/dev-scripts/fill-metadata.py "$BOOK_ID" 10 --model gemini-2.5-flash-lite
```

## Book IDs for ingested books

| Book | UUID |
|------|------|
| Structure and Interpretation of Computer Programs | `62e581b4-9d31-4422-9100-7b6be671323d` |
| Just Use Postgres | `11367f49-2f44-4bbb-9a7d-f5b2daab744b` |
