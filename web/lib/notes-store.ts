import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { NoteSessionResponse } from "@/types/notes";

/**
 * Cached note lists, one per book, persisted to localStorage.
 *
 * The same shape the chat store already uses, for the same reason: a request to
 * this database costs around a second, so a panel that re-queries on every open
 * feels broken. The list paints from memory first and is refreshed in the
 * background only when the entry is old or has been marked stale.
 */

/** How long a cached list is trusted before it is refreshed in the background. */
const CACHE_TTL_MS = 30 * 60 * 1000;

export interface NotesCacheEntry {
  sessions: NoteSessionResponse[];
  total: number;
  /** Epoch millis of the request that produced this entry. */
  fetchedAt: number;
}

interface NotesCacheState {
  byBook: Record<string, NotesCacheEntry>;
  save: (
    bookId: string,
    sessions: NoteSessionResponse[],
    total: number,
  ) => void;
  /** Mark a book's list as needing a refresh, keeping what is cached so the
   *  panel can still paint it while the refresh runs. */
  touch: (bookId: string) => void;
  drop: (bookId: string) => void;
}

export const useNotesCache = create<NotesCacheState>()(
  persist(
    (set) => ({
      byBook: {},
      save: (bookId, sessions, total) =>
        set((state) => ({
          byBook: {
            ...state.byBook,
            [bookId]: { sessions, total, fetchedAt: Date.now() },
          },
        })),
      touch: (bookId) =>
        set((state) => {
          const entry = state.byBook[bookId];
          if (!entry) return state;
          return {
            byBook: { ...state.byBook, [bookId]: { ...entry, fetchedAt: 0 } },
          };
        }),
      drop: (bookId) =>
        set((state) => {
          const next = { ...state.byBook };
          delete next[bookId];
          return { byBook: next };
        }),
    }),
    {
      name: "folio-notes-cache",
      // Entries past the TTL are useless on load: drop them rather than render
      // a list from an earlier session as if it were current.
      onRehydrateStorage: () => (state) => {
        if (!state) return;
        const now = Date.now();
        const fresh: Record<string, NotesCacheEntry> = {};
        for (const [bookId, entry] of Object.entries(state.byBook)) {
          if (entry && now - entry.fetchedAt < CACHE_TTL_MS) {
            fresh[bookId] = entry;
          }
        }
        state.byBook = fresh;
      },
    },
  ),
);

/** True when the entry is recent enough to render without refreshing. */
export function isFresh(entry: NotesCacheEntry | undefined): boolean {
  return !!entry && Date.now() - entry.fetchedAt < CACHE_TTL_MS;
}
