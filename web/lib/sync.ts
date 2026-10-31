import { apiClient } from "./api-client";
import { useChatStore } from "./chat-store";
import { useNotesStore, type LocalNote } from "./notes-store";
import { markNoteSynced, flushNoteSyncNow } from "./note-sync";
import type { NoteDetail } from "@/types/notes";

/**
 * Cache-miss sync: the browser (localStorage) is the cache. On a cache miss —
 * no local data for this user + book — pull the *current user's* records from
 * the server; on a cache hit, use local and never hit the network.
 *
 * Every endpoint here is user-scoped server-side (`get_current_user`), so when
 * auth is wired in, "import" means "this user's notes/chat", not everyone's.
 * Today auth is anonymous, so everyone shares one user id — the code is already
 * correct, only the identity is a placeholder.
 */

/** Convert a server note detail into a local note (one-time import). */
export function toLocalNote(detail: NoteDetail): LocalNote {
  return {
    id: detail.id,
    bookId: detail.book_id,
    title: detail.title,
    source: detail.source === "ai_generated" ? "ai_generated" : "typed",
    createdAt: new Date(detail.created_at).getTime(),
    updatedAt: detail.updated_at
      ? new Date(detail.updated_at).getTime()
      : new Date(detail.created_at).getTime(),
    blocks: detail.blocks.map((block) => ({
      id: block.id,
      kind: block.kind,
      text: block.text,
      origin: block.origin,
      links: block.links.map((link) => ({
        id: link.id,
        section_id: link.section_id,
        anchor_heading_path: link.anchor_heading_path,
        page_start: link.page_start,
        page_end: link.page_end,
        excerpt: link.excerpt,
        status: link.status,
        origin: link.origin,
      })),
    })),
  };
}

/** Import this user's notes for a book, only on a cache miss. */
export async function importNotesForBook(
  bookId: string,
  options: { force?: boolean } = {},
): Promise<void> {
  const store = useNotesStore.getState();
  if (!options.force && store.listNotes(bookId).length > 0) return; // cache hit

  const data = await apiClient.listNoteSessions(bookId, { limit: 500 });
  for (const session of data.sessions) {
    try {
      const detail = await apiClient.getNote(session.id);
      store.saveNote(toLocalNote(detail));
      markNoteSynced(detail.id); // already on the server; don't re-push it
    } catch {
      // skip a note that fails to load
    }
  }
}

/** Import this user's chat history for a book, only on a cache miss (or force). */
export async function importChatForBook(
  bookId: string,
  options: { force?: boolean } = {},
): Promise<void> {
  const store = useChatStore.getState();
  if (options.force) {
    // A manual sync reconciles chat from the server: drop the local view and
    // rebuild it from the recorded turns (which include other devices').
    for (const session of store.listSessions(bookId)) store.deleteSession(session.id);
  } else if (store.listSessions(bookId).length > 0) {
    return; // cache hit
  }

  const data = await apiClient.listQaTurns({ bookId, limit: 200 });
  const turns = [...data.turns].reverse(); // oldest first
  if (turns.length === 0) return;

  // The server stores a flat Q&A log, not sessions; rebuild it as one chat.
  const sessionId = store.createSession(bookId);
  for (const turn of turns) {
    store.addMessage(sessionId, { role: "user", text: turn.question });
    store.addMessage(sessionId, {
      role: "ai",
      text: turn.answer,
      citations: (turn.sources ?? []).map((source) => ({
        passage: source.passage,
        sectionHeading: source.section_heading,
        pageStart: source.page_start,
        pageEnd: source.page_end,
        excerpt: source.excerpt,
      })),
      notCovered: null,
    });
  }
}

/** Cache-miss sync for both notes and chat (per user). Cache hit = local. */
export async function syncUserData(bookId: string): Promise<void> {
  await Promise.allSettled([
    importNotesForBook(bookId),
    importChatForBook(bookId),
  ]);
}

/**
 * Manual cross-device sync: push this device's pending note edits to the server,
 * then pull the server's current notes + chat so changes made on another device
 * (phone vs laptop) show up here. Rate limiting is handled by the caller.
 */
export async function syncBook(bookId: string): Promise<void> {
  await flushNoteSyncNow(); // push local edits first so they aren't overwritten
  await Promise.allSettled([
    importNotesForBook(bookId, { force: true }),
    importChatForBook(bookId, { force: true }),
  ]);
}
