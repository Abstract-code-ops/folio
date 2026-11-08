# 7. How to add books

Adding a book = **(1) put the PDF somewhere public** → **(2) register it in the admin page**
→ **(3) run ingestion** → **(4) verify**.

> ⚠️ **Licensing:** only add books you have the **right to redistribute** (public domain,
> CC-licensed OER like OpenStax/SICP, or author-permitted). Do **not** host copyrighted
> books or pirated PDFs. See the licensing notes at the end.

## Step 1 — Upload the PDF to storage
Upload to Supabase Storage (bucket `book-pdfs`, public) or any **publicly reachable PDF URL**.
The URL becomes the book's `storage_url`.

```bash
# Supabase REST upload (service-role key)
curl -X POST "$SUPABASE_URL/storage/v1/object/book-pdfs/my-book.pdf" \
  -H "Authorization: Bearer $SUPABASE_SERVICE_ROLE_KEY" \
  -H "x-upsert: true" -H "Content-Type: application/pdf" \
  --data-binary @my-book.pdf
# public URL:
#   $SUPABASE_URL/storage/v1/object/public/book-pdfs/my-book.pdf
```
Verify it's reachable (200 + application/pdf):
```bash
docker exec folio-api-1 python3 /app/scripts/check_book_urls.py
```

## Step 2 — Register in the admin page
1. Sign in as an **admin** (email in `ADMIN_EMAILS`).
2. Open **/admin → Ingest books** (`/ingest`).
3. Expand **Add a book**; fill **Title**, **Author**, **Category** (e.g. `Databases`), and
   **PDF public URL**; click **Add book**.
4. Select the new book in the list.

![Add book form](./assets/07-add-book-form.png)
<!-- CAPTURE: /admin → Ingest → "Add a book" expanded with fields filled. -->

## Step 3 — Run ingestion
Click **Start ingestion** (or **Re-ingest (force)** for an already-completed book). Watch the
live console: sections, chunks, tables, figures tick up. For a book > 12 MB it will first
**optimize** the PDF (Ghostscript `/ebook` → smaller file, `storage_url` repointed) then parse.

GIF: add + ingest
![Add and ingest demo](./assets/07-add-and-ingest.gif)
<!-- GIF (15–25s): fill Add-a-book → Start ingestion → progress console advancing → status "Ready". -->

Console statuses: `not_started → processing → completed` (or `failed`).
The book **appears in `/library` only once `completed`**.

### CLI alternative (most reliable, full logs)
```bash
docker exec folio-api-1 python3 /app/ingest.py <book_id> gemini-2.5-flash-lite
```
Watch for `[PIPELINE] Parsed N sections, W words` (large W = good text layer), then
`Detected N figure region(s)` → `Captioned M figure(s)` → `✓ Ingestion complete`.

## Step 4 — Verify
```bash
docker exec folio-api-1 python3 /app/scripts/test_figure_caption.py <book_id>
# chunks by kind: {'text': …, 'table': …, 'figure': …}
```

## Categorize / edit / delete
- **Category**: in the selected book panel, edit **Category** → **Save category**
  (`PATCH /books/{id}`). Library category chips update from the data.
- **Delete**: **Delete book** (removes the book + sections/chunks/coverage/notes/QA).

## Troubleshooting
| Symptom | Check |
|---------|-------|
| Book never loads in reader | `check_book_urls.py`; huge PDFs (>30 MB) strain the WASM viewer — optimization kicks in at 12 MB |
| "0 words" / guard FAILED | PDF has no text layer (scanned/corrupt) — use a text PDF |
| Figures = 0 | run `debug_figures.py <id>`; inspect caption (empty vs error) |
| `EMAXCONNSESSION` | don't raise DB pool sizes (15-client Supabase cap) |

## Licensing (short)
- ✅ **Public domain** (Project Gutenberg), **CC-BY** (OpenStax), **CC-BY-SA** (SICP — attribute + share-alike), author-permitted free PDFs.
- ❌ **Copyrighted** (O'Reilly etc.) and **pirated** aggregators (Dokumen.pub, libgen).
- Record each book's license + source; show attribution (CC requires it).
