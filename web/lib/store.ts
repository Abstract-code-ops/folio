import { create } from "zustand";
import type { BookResponse } from "@/types/books";
import { apiClient } from "@/lib/api-client";

// ── Books library cache ──────────────────────────────────────

interface BooksState {
  books: BookResponse[];
  booksLoading: boolean;
  booksError: string | null;
  fetchBooks: () => void;
}

export const useBooksStore = create<BooksState>((set, get) => ({
  books: [],
  booksLoading: true,
  booksError: null,

  fetchBooks: async () => {
    // Don't re-fetch if we already have data
    if (get().books.length > 0 && !get().booksLoading) return;

    set({ booksLoading: true, booksError: null });
    try {
      const res = await apiClient.listBooks();
      set({ books: res.books, booksLoading: false });
    } catch (err) {
      set({
        booksError: err instanceof Error ? err.message : "Failed to load books",
        booksLoading: false,
      });
    }
  },
}));
