# Folio

**Ask the great books questions. Get answers with the exact page.**

Folio is a study platform built around a small, hand-picked shelf of open-access textbooks. Read the book, ask it questions, and get answers that cite the pages they came from. Turn any topic into study notes whose every claim links back to the source.


## Why Folio exists

Most foundational knowledge comes from people who spent years learning something the hard way, then poured that experience into a book. Those books are some of the best teachers there are, but they are long, dense, and easy to get lost in.

Folio doesn't replace them. It makes them easier to learn from, and keeps you pointed back at the original words. If an answer can't be traced to a page, it shouldn't be trusted.

## What it does

- **Read** the full PDF in the browser, with a study panel beside it.
- **Chat with the book.** Answers are grounded in the text and cite the pages they used. Click a citation to jump there.
- **Generate notes** from a topic or a chapter range, with source links on every note.
- **Write your own notes** and (in progress) have Folio suggest links to the passages they relate to.
- **Curated library.** The book list is chosen by a person, not scraped. Only the curator ingests books, and only books that can legally be redistributed (public domain, Creative Commons, or with the author's permission).
- **Coverage map** (planned): see which parts of a book you've studied.

## How it works

```
PDF ──► parse (text, tables, figures)
    ──► split by the book's table of contents
        (chapters → sections → subsections, plus connective text)
    ──► enrich (summaries, key concepts, definitions, figure captions)
    ──► embed (pgvector)

Question ──► retrieve the closest passages ──► answer using only those passages
         ──► cite the pages actually used
```

A few design choices worth knowing:

- **Structure-aware chunking.** Books are split along their own table of contents, so retrieval can use the chapter and section a passage belongs to, not just similar-looking text.
- **Grounded answers.** The model is told to answer only from retrieved passages and to say so when the book doesn't cover something.
- **Measured, not guessed.** A built-in evaluation harness tracks retrieval quality (hit rate, MRR) so pipeline changes are judged by numbers.

## Tech stack

| Layer | Technology |
|-------|------------|
| Web | Next.js (App Router), Tailwind CSS, shadcn/ui |
| API | FastAPI, SQLAlchemy 2, Alembic |
| Database | PostgreSQL with pgvector |
| Auth | Better Auth, admin allow-list, limited guest mode |
| Embeddings | Ollama (`nomic-embed-text`, local) |
| Answers and notes | OpenAI-compatible provider (configurable) |
| Metadata and figure captions | Google Gemini |
| PDF processing | PyMuPDF, Ghostscript, Tesseract (OCR fallback) |
| Packaging | Docker Compose |

## Quick start

**Requirements:** Docker 24+, Docker Compose v2, about 4 GB free RAM, 5 GB disk.

```bash
git clone https://github.com/<your-username>/folio.git
cd folio

cp .env.example .env     # then fill in the values (see below)
docker compose up -d

curl http://localhost:8000/books   # → 200 []
```

Open <http://localhost:3000>.

Key settings in `.env`:

```dotenv
DATABASE_URL=...                 # Postgres with the pgvector extension
DATABASE_URL_ASYNC=...           # Postgress url for async operations
SUPABASE_URL=...                 # or any public PDF storage
SUPABASE_SERVICE_ROLE_KEY=...
SUPABASE_ANON_KEY=...
BETTER_AUTH_SECRET=...
BETTER_AUTH_URL=...
AUTH_REQUIRED=true
NEXT_PUBLIC_AUTH_ENABLED=true
ADMIN_EMAILS=you@example.com     # who can add and ingest books
GEMINI_API_KEY=...
VOID_API_KEY=...                 # answer/notes provider; swap via VOID_API_BASE / VOID_MODEL
NEXT_PUBLIC_SENTRY_DSN=...       # for error tracking
SENTRY_DSN=...
SENTRY_AUTH_TOKEN=...
NEXT_PUBLIC_POSTHOG_KEY=...      #observability
NEXT_PUBLIC_POSTHOG_HOST=...
```

## Documentation

Step-by-step operator guides live in [`docs/setup`](./docs/setup):

1. [Installation](./docs/setup/01-installation.md)
2. [Database](./docs/setup/02-database.md)
3. [Vector database](./docs/setup/03-vector-database.md)
4. [AI providers](./docs/setup/04-ai-providers.md)
5. [Authentication](./docs/setup/05-authentication.md)
6. [Deployment](./docs/setup/06-deployment.md)
7. [Adding books](./docs/setup/07-adding-books.md)

## A note on books and licensing

Folio only hosts books it has the right to redistribute. Before adding one, check its license. "Free to read" is not the same as "free to redistribute." Do not add copyrighted books or pirated PDFs. If you believe something here is hosted improperly, open an issue or contact the maintainer and it will be removed promptly.

## Status

Folio is an actively developed personal project. Expect rough edges. Current work:

- [ ] Curated topics and a redesigned landing page
- [ ] Topic-based notes with clickable source links
- [ ] Automatic source links for notes you write yourself
- [ ] Retrieval improvements (page-aware chunks, hybrid search), tracked by the eval harness
- [ ] Coverage map
- [ ] Web search to supplement book answers, with clearly separated sources

## Contributing

Issues and ideas are welcome. Please open an issue before sending a large pull request.

## License

The code is licensed under **APGL-3.0**. The books in the library keep their own licenses, shown on each book's page.

