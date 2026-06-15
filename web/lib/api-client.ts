// Typed HTTP client for FastAPI

import type { BookListResponse, BookResponse, IngestionStatus } from "@/types/books";
import type { CoverageMapResponse } from "@/types/coverage";
import type { NoteSessionResponse, NoteSource } from "@/types/notes";

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

class ApiClient {
  private baseUrl: string;

  constructor(baseUrl: string = BASE_URL) {
    this.baseUrl = baseUrl;
  }

  // ── Books ──────────────────────────────────────────────────

  async listBooks(options?: {
    status?: IngestionStatus;
    limit?: number;
    offset?: number;
  }): Promise<BookListResponse> {
    const params = new URLSearchParams();
    if (options?.status) params.set("status", options.status);
    if (options?.limit) params.set("limit", String(options.limit));
    if (options?.offset) params.set("offset", String(options.offset));

    const query = params.toString();
    const url = `${this.baseUrl}/books${query ? `?${query}` : ""}`;

    const res = await fetch(url);
    if (!res.ok) {
      throw new Error(`Failed to fetch books: ${res.statusText}`);
    }
    return res.json() as Promise<BookListResponse>;
  }

  // ── Coverage ──────────────────────────────────────────────

  async getCoverageMap(bookId: string): Promise<CoverageMapResponse> {
    const url = `${this.baseUrl}/coverage/${bookId}`;
    const res = await fetch(url);
    if (!res.ok) {
      throw new Error(`Failed to fetch coverage map: ${res.statusText}`);
    }
    return res.json() as Promise<CoverageMapResponse>;
  }

  // ── Notes ───────────────────────────────────────────────────

  async createNoteSession(params: {
    book_id: string;
    raw_text: string;
    source: NoteSource;
    title?: string;
  }): Promise<NoteSessionResponse> {
    const url = `${this.baseUrl}/notes`;
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(params),
    });
    if (!res.ok) {
      throw new Error(`Failed to create note session: ${res.statusText}`);
    }
    return res.json() as Promise<NoteSessionResponse>;
  }

  async getBook(bookId: string, loadSections?: boolean): Promise<BookResponse> {
    const params = loadSections ? "?load_sections=true" : "";
    const url = `${this.baseUrl}/books/${bookId}${params}`;

    const res = await fetch(url);
    if (res.status === 404) {
      throw new Error("Book not found");
    }
    if (!res.ok) {
      throw new Error(`Failed to fetch book: ${res.statusText}`);
    }
    return res.json() as Promise<BookResponse>;
  }
}

export const apiClient = new ApiClient();
export { ApiClient };
