// Typed HTTP client for FastAPI

import type { BookListResponse, BookResponse, IngestionStatus } from "@/types/books";
import type { CoverageMapResponse } from "@/types/coverage";
import type {
  GeneratedSectionNotes,
  NoteSessionListResponse,
  NoteSessionResponse,
  NoteSource,
} from "@/types/notes";
import type { QaEvent } from "@/types/chat";

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

  // ── Q&A ─────────────────────────────────────────────────────

  async askQuestion(
    bookId: string,
    question: string,
  ): Promise<ReadableStream<QaEvent>> {
    const url = `${this.baseUrl}/qa/${bookId}`;
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });
    if (!res.ok) {
      throw new Error(`Failed to ask question: ${res.statusText}`);
    }
    if (!res.body) {
      throw new Error("Response body is null — streaming not supported");
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    return new ReadableStream<QaEvent>({
      async start(controller) {
        try {
          while (true) {
            const { done, value } = await reader.read();
            if (done) {
              if (buffer.trim()) {
                try {
                  controller.enqueue(JSON.parse(buffer));
                } catch {
                  // skip malformed trailing data
                }
              }
              controller.close();
              return;
            }
            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split("\n");
            buffer = lines.pop() ?? "";

            for (const line of lines) {
              const trimmed = line.trim();
              if (!trimmed) continue;
              try {
                const parsed = JSON.parse(trimmed) as QaEvent;
                controller.enqueue(parsed);
              } catch {
                // skip malformed lines
              }
            }
          }
        } catch (e) {
          controller.error(e);
        }
      },
    });
  }

  // ── Notes ───────────────────────────────────────────────────

  async listNoteSessions(
    bookId: string,
    options?: { limit?: number; offset?: number },
  ): Promise<NoteSessionListResponse> {
    const params = new URLSearchParams({ book_id: bookId });
    if (options?.limit) params.set("limit", String(options.limit));
    if (options?.offset) params.set("offset", String(options.offset));
    const url = `${this.baseUrl}/notes?${params.toString()}`;
    const res = await fetch(url);
    if (!res.ok) {
      throw new Error(`Failed to list note sessions: ${res.statusText}`);
    }
    return res.json() as Promise<NoteSessionListResponse>;
  }

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

  async generateNotes(
    bookId: string,
    chapterStart: number,
    chapterEnd: number,
  ): Promise<ReadableStream<GeneratedSectionNotes>> {
    const url = `${this.baseUrl}/notes/generate`;
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        book_id: bookId,
        chapter_start: chapterStart,
        chapter_end: chapterEnd,
      }),
    });
    if (!res.ok) {
      throw new Error(`Failed to generate notes: ${res.statusText}`);
    }
    if (!res.body) {
      throw new Error("Response body is null — streaming not supported");
    }

    // Wrap the byte ReadableStream into a JSON-object ReadableStream
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    return new ReadableStream<GeneratedSectionNotes>({
      async start(controller) {
        try {
          while (true) {
            const { done, value } = await reader.read();
            if (done) {
              // Flush remaining buffer
              if (buffer.trim()) {
                try {
                  controller.enqueue(JSON.parse(buffer));
                } catch {
                  // skip malformed trailing data
                }
              }
              controller.close();
              return;
            }
            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split("\n");
            // Keep the last (potentially incomplete) line in the buffer
            buffer = lines.pop() ?? "";

            for (const line of lines) {
              const trimmed = line.trim();
              if (!trimmed) continue;
              try {
                const parsed = JSON.parse(trimmed) as GeneratedSectionNotes;
                controller.enqueue(parsed);
              } catch {
                // skip malformed lines (e.g. error placeholders)
              }
            }
          }
        } catch (e) {
          controller.error(e);
        }
      },
    });
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
