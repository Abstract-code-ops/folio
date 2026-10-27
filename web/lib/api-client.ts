// Typed HTTP client for FastAPI

import type { BookListResponse, BookResponse, IngestionStatus } from "@/types/books";
import type { CoverageMapResponse } from "@/types/coverage";
import type {
  GeneratedSectionNotes,
  NoteBlockDraft,
  NoteDetail,
  NoteSessionListResponse,
  NoteSessionResponse,
  NoteSource,
  NoteTopicEvent,
} from "@/types/notes";import type { QaEvent, SummarizeResponse } from "@/types/chat";
import type { QaTurnListResponse } from "@/types/qa-turns";

// Use a relative proxy URL so the browser talks to Next.js (same origin),
// which forwards to the FastAPI backend inside the Docker network.
// Override via NEXT_PUBLIC_API_URL env var if needed.
const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "/api/proxy";

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

  /**
   * Recent Q&A turns with diagnostics, for the eval page.
   * Newest first; scoped to the current user.
   */
  async listQaTurns(options?: {
    bookId?: string;
    limit?: number;
  }): Promise<QaTurnListResponse> {
    const params = new URLSearchParams();
    if (options?.bookId) params.set("book_id", options.bookId);
    if (options?.limit) params.set("limit", String(options.limit));

    const query = params.toString();
    const url = `${this.baseUrl}/qa/turns${query ? `?${query}` : ""}`;

    const res = await fetch(url);
    if (!res.ok) {
      throw new Error(`Failed to fetch turns: ${res.statusText}`);
    }
    return res.json() as Promise<QaTurnListResponse>;
  }

  async askQuestion(
    bookId: string,
    question: string,
    options?: {
      summary?: string;
      history?: { role: string; content: string }[];
    },
  ): Promise<ReadableStream<QaEvent>> {
    const url = `${this.baseUrl}/qa/${bookId}`;
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        question,
        summary: options?.summary,
        history: options?.history ?? [],
      }),
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

  async summarizeConversation(
    messages: { role: string; content: string }[],
  ): Promise<string> {
    const url = `${this.baseUrl}/qa/summarize`;
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ messages }),
    });
    if (!res.ok) {
      throw new Error(`Failed to summarize conversation: ${res.statusText}`);
    }
    const data = (await res.json()) as SummarizeResponse;
    return data.summary;
  }

  async listNoteSessions(
    bookId: string,
    options?: { limit?: number; offset?: number; sectionId?: string },
  ): Promise<NoteSessionListResponse> {
    const params = new URLSearchParams({ book_id: bookId });
    if (options?.limit) params.set("limit", String(options.limit));
    if (options?.offset) params.set("offset", String(options.offset));
    if (options?.sectionId) params.set("section_id", options.sectionId);
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

    return this.ndjson<GeneratedSectionNotes>(res.body);
  }

  // ── Note documents ─────────────────────────────────────────────

  async createNoteDocument(params: {
    book_id: string;
    blocks?: NoteBlockDraft[];
    title?: string;
    source?: NoteSource;
  }): Promise<NoteDetail> {
    const url = `${this.baseUrl}/notes/document`;
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(params),
    });
    if (!res.ok) {
      throw new Error(`Failed to create note: ${res.statusText}`);
    }
    return res.json() as Promise<NoteDetail>;
  }

  async getNote(noteId: string): Promise<NoteDetail> {
    const url = `${this.baseUrl}/notes/${noteId}`;
    const res = await fetch(url);
    if (res.status === 404) {
      throw new Error("Note not found");
    }
    if (!res.ok) {
      throw new Error(`Failed to load note: ${res.statusText}`);
    }
    return res.json() as Promise<NoteDetail>;
  }

  async saveNoteBlocks(
    noteId: string,
    blocks: NoteBlockDraft[],
  ): Promise<NoteDetail> {
    const url = `${this.baseUrl}/notes/${noteId}/blocks`;
    const res = await fetch(url, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ blocks }),
    });
    if (res.status === 404) {
      throw new Error("Note not found");
    }
    if (!res.ok) {
      throw new Error(`Failed to save note: ${res.statusText}`);
    }
    return res.json() as Promise<NoteDetail>;
  }

  /**
   * Decode an NDJSON response into objects.
   *
   * One decoder for every streamed endpoint, because the fiddly part — holding a
   * partial line in the buffer and skipping a malformed one instead of killing
   * the stream — is exactly the sort of thing that drifts when it is copied.
   */
  private ndjson<T>(body: ReadableStream<Uint8Array>): ReadableStream<T> {
    const reader = body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    return new ReadableStream<T>({
      async start(controller) {
        try {
          while (true) {
            const { done, value } = await reader.read();
            if (done) {
              // Flush whatever is left in the buffer.
              if (buffer.trim()) {
                try {
                  controller.enqueue(JSON.parse(buffer) as T);
                } catch {
                  // skip malformed trailing data
                }
              }
              controller.close();
              return;
            }
            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split("\n");
            // Keep the last (potentially incomplete) line in the buffer.
            buffer = lines.pop() ?? "";

            for (const line of lines) {
              const trimmed = line.trim();
              if (!trimmed) continue;
              try {
                controller.enqueue(JSON.parse(trimmed) as T);
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

  async generateTopicNotes(
    bookId: string,
    topic: string,
  ): Promise<ReadableStream<NoteTopicEvent>> {
    const url = `${this.baseUrl}/notes/topic`;
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ book_id: bookId, topic }),
    });
    if (!res.ok) {
      throw new Error(`Failed to generate notes: ${res.statusText}`);
    }
    if (!res.body) {
      throw new Error("Response body is null — streaming not supported");
    }
    return this.ndjson<NoteTopicEvent>(res.body);
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
