// Admin-only API helpers for the ingest page.
//
// Kept separate from the main `api-client.ts` so the admin surface is
// self-contained. Every call goes through the same-origin `/api/proxy`
// (which attaches the Better Auth session); the FastAPI side enforces
// `require_admin` on the mutating endpoints.
//
// `ngrok-skip-browser-warning` opts out of ngrok's free-tier HTML interstitial
// so a proxied JSON request never comes back as an ngrok HTML page.

import type { BookResponse, IngestionStatus } from "@/types/books";

const BASE_URL = process.env.NEXT_PUBLIC_API_URL || "/api/proxy";
const EXTRA_HEADERS = { "ngrok-skip-browser-warning": "true" };

export interface IngestProgress {
  book_id: string;
  status: IngestionStatus;
  sections_total: number | null;
  sections_done: number;
  chunks: number;
  figures: number;
  tables: number;
  word_count: number | null;
  running: boolean;
}

/** Turn a failed response into a short, readable message (never raw HTML). */
async function errorText(res: Response, fallback: string): Promise<string> {
  const body = await res.text().catch(() => "");
  const trimmed = body.trimStart();
  if (trimmed.startsWith("<")) {
    return `${fallback} (HTTP ${res.status}) — the server returned an HTML page, not JSON. The API may be unreachable through the proxy, or the ngrok tunnel served its browser-warning page.`;
  }
  if (!body) return `${fallback} (HTTP ${res.status} ${res.statusText})`;
  try {
    const parsed = JSON.parse(body);
    if (parsed && typeof parsed.detail === "string") {
      return `${parsed.detail} (HTTP ${res.status})`;
    }
  } catch {
    /* not JSON — fall through */
  }
  return body.length > 300 ? `${body.slice(0, 300)}…` : body;
}

export async function listAllBooks(): Promise<BookResponse[]> {
  const res = await fetch(`${BASE_URL}/books?limit=200`, { headers: EXTRA_HEADERS });
  if (!res.ok) throw new Error(await errorText(res, "Failed to load books"));
  const data = (await res.json()) as { books: BookResponse[] };
  return data.books;
}

export async function triggerIngest(bookId: string, force = false): Promise<void> {
  const url = `${BASE_URL}/books/${bookId}/ingest${force ? "?force=true" : ""}`;
  const res = await fetch(url, { method: "POST", headers: EXTRA_HEADERS });
  if (!res.ok) throw new Error(await errorText(res, "Failed to start ingest"));
}

export async function getIngestStatus(bookId: string): Promise<IngestProgress> {
  const res = await fetch(`${BASE_URL}/books/${bookId}/ingest/status`, {
    headers: EXTRA_HEADERS,
  });
  if (!res.ok) throw new Error(await errorText(res, "Failed to load status"));
  return (await res.json()) as IngestProgress;
}

export async function createBook(params: {
  title: string;
  author: string;
  category?: string;
  storage_url: string;
  description?: string;
}): Promise<BookResponse> {
  const res = await fetch(`${BASE_URL}/books`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...EXTRA_HEADERS },
    body: JSON.stringify(params),
  });
  if (!res.ok) throw new Error(await errorText(res, "Failed to add book"));
  return (await res.json()) as BookResponse;
}

export async function updateBookCategory(
  bookId: string,
  category: string | null,
): Promise<BookResponse> {
  const res = await fetch(`${BASE_URL}/books/${bookId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json", ...EXTRA_HEADERS },
    body: JSON.stringify({ category }),
  });
  if (!res.ok) throw new Error(await errorText(res, "Failed to update category"));
  return (await res.json()) as BookResponse;
}

export async function deleteBook(bookId: string): Promise<void> {
  const res = await fetch(`${BASE_URL}/books/${bookId}`, {
    method: "DELETE",
    headers: EXTRA_HEADERS,
  });
  if (!res.ok) throw new Error(await errorText(res, "Failed to delete book"));
}
