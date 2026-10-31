import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";
import type { BookResponse } from "@/types/books";
import { apiClient } from "@/lib/api-client";

// ── Books library cache ──────────────────────────────────────
//
// Books are a *global* shared resource (same for every user), so this cache is
// not user-scoped. It persists to localStorage and revalidates in the
// background: a back-navigation or reload paints the cached list instantly and
// only refetches when the data is older than TTL. `booksLoading` stays true only
// while there is nothing to show, so a background refresh never flashes a
// spinner over content that already exists.

const TTL_MS = 5 * 60 * 1000;

interface BooksState {
  books: BookResponse[];
  booksLoading: boolean;
  booksError: string | null;
  lastFetched: number | null;
  fetchBooks: (opts?: { force?: boolean }) => Promise<void>;
}

export const useBooksStore = create<BooksState>()(
  persist(
    (set, get) => ({
      books: [],
      booksLoading: true,
      booksError: null,
      lastFetched: null,

      fetchBooks: async (opts) => {
        const { books, booksLoading, lastFetched } = get();
        const fresh =
          books.length > 0 && lastFetched !== null && Date.now() - lastFetched < TTL_MS;

        if (!opts?.force && fresh) return; // cache hit — no network
        if (booksLoading && books.length > 0) return; // a refresh is already in flight

        set({ booksLoading: books.length === 0, booksError: null });
        try {
          const res = await apiClient.listBooks();
          set({ books: res.books, booksLoading: false, lastFetched: Date.now() });
        } catch (err) {
          set({
            booksError: err instanceof Error ? err.message : "Failed to load books",
            booksLoading: false,
          });
        }
      },
    }),
    {
      name: "folio-books-cache",
      storage: createJSONStorage(() =>
        typeof localStorage === "undefined"
          ? { getItem: () => null, setItem: () => {}, removeItem: () => {} }
          : localStorage,
      ),
      onRehydrateStorage: () => (state) => {
        // Cached books exist → don't show a full-screen loader on load.
        if (state && state.books.length > 0) state.booksLoading = false;
      },
      // Never trust a stale list on load: paint it, but let fetchBooks revalidate.
      partialize: (state) => ({
        books: state.books,
        lastFetched: state.lastFetched,
      }),
    },
  ),
);
