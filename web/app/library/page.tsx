"use client";

import { useEffect, useMemo, useState } from "react";
import { BookOpen, Search, Library } from "lucide-react";
import Link from "next/link";
import { useBooksStore } from "@/lib/store";
import { Loader } from "@/components/ui/loader";
import { cn } from "@/lib/utils";
import { AuthNav } from "@/components/auth/auth-nav";
import type { IngestionStatus, BookResponse } from "@/types/books";

const STATUS_LABEL: Record<IngestionStatus, string> = {
  not_started: "Not started",
  processing: "Processing…",
  completed: "Ready",
  failed: "Failed",
};

const STATUS_DOT: Record<IngestionStatus, string> = {
  not_started: "bg-text-subtle",
  processing: "bg-state-warning",
  completed: "bg-state-success",
  failed: "bg-state-error",
};

const FILTERS: { id: IngestionStatus | "all"; label: string }[] = [
  { id: "all", label: "All" },
  { id: "completed", label: "Ready" },
  { id: "processing", label: "Processing" },
  { id: "not_started", label: "Not started" },
];

function BookCover({
  title,
  cover_image_url,
}: {
  title: string;
  cover_image_url: string | null;
}) {
  if (cover_image_url) {
    return (
      <img
        src={cover_image_url}
        alt={`${title} cover`}
        className="h-full w-full object-cover"
      />
    );
  }
  return (
    <div className="flex h-full w-full flex-col items-center justify-center gap-1.5 bg-gradient-to-br from-accent/30 to-accent/5 px-3 text-center">
      <BookOpen className="h-5 w-5 text-accent/70" strokeWidth={1.5} />
      <span className="font-heading text-body-sm font-semibold text-accent line-clamp-3">
        {title}
      </span>
    </div>
  );
}

function BookCard({ book }: { book: BookResponse }) {
  return (
    <Link
      href={`/reader?id=${book.id}`}
      className="group flex flex-col overflow-hidden rounded-xl bg-bg-elevated border border-border transition-all duration-150 ease-out hover:border-accent/40 hover:shadow-md active:scale-[0.97] active:bg-bg-surface"
    >
      <div className="relative aspect-[3/4] bg-bg-surface">
        <BookCover title={book.title} cover_image_url={book.cover_image_url} />
        <span className="absolute right-2 top-2 flex items-center gap-1.5 rounded-full bg-bg-base/80 px-2 py-0.5 backdrop-blur">
          <span
            className={cn(
              "h-1.5 w-1.5 rounded-full",
              STATUS_DOT[book.ingestion_status],
            )}
          />
          <span className="text-body-sm text-text-muted">
            {STATUS_LABEL[book.ingestion_status]}
          </span>
        </span>
      </div>
      <div className="flex flex-col gap-1 p-4">
        <h3 className="font-heading text-body font-semibold text-text-primary truncate">
          {book.title}
        </h3>
        <p className="text-body-sm text-text-muted truncate">{book.author}</p>
        {book.section_count !== null && (
          <p className="text-body-sm text-text-subtle mt-1">
            {book.section_count} sections
          </p>
        )}
      </div>
    </Link>
  );
}

function SkeletonGrid() {
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
      {Array.from({ length: 8 }).map((_, index) => (
        <div
          key={index}
          className="flex flex-col overflow-hidden rounded-xl border border-border bg-bg-elevated"
        >
          <div className="aspect-[3/4] animate-pulse bg-bg-surface" />
          <div className="space-y-2 p-4">
            <div className="h-3.5 w-3/4 animate-pulse rounded bg-bg-surface" />
            <div className="h-3 w-1/2 animate-pulse rounded bg-bg-surface" />
          </div>
        </div>
      ))}
    </div>
  );
}

export default function LibraryPage() {
  const books = useBooksStore((s) => s.books);
  const loading = useBooksStore((s) => s.booksLoading);
  const error = useBooksStore((s) => s.booksError);
  const fetchBooks = useBooksStore((s) => s.fetchBooks);

  const [query, setQuery] = useState("");
  const [status, setStatus] = useState<IngestionStatus | "all">("all");

  useEffect(() => {
    fetchBooks();
  }, [fetchBooks]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return books.filter((b) => {
      const matchesQuery =
        !q ||
        b.title.toLowerCase().includes(q) ||
        (b.author ?? "").toLowerCase().includes(q);
      const matchesStatus = status === "all" || b.ingestion_status === status;
      return matchesQuery && matchesStatus;
    });
  }, [books, query, status]);

  return (
    <div className="min-h-screen bg-bg-base">
      {/* Header */}
      <header className="sticky top-0 z-10 flex items-center justify-between px-6 h-14 border-b border-border-subtle bg-bg-base/80 backdrop-blur">
        <div className="flex items-center gap-3">
          <BookOpen className="h-5 w-5 text-accent" />
          <span className="font-heading text-body font-semibold text-text-primary">
            Folio
          </span>
        </div>
        <AuthNav />
      </header>

      {/* Content */}
      <main className="mx-auto max-w-5xl px-6 py-10">
        <div className="mb-8">
          <h1 className="font-heading text-h3 text-text-primary">Library</h1>
          <p className="text-body text-text-muted mt-1">
            Open-access CS and software engineering textbooks.
          </p>
        </div>

        {/* Search + filters */}
        <div className="mb-8 space-y-4">
          <div className="relative">
            <Search
              className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-text-subtle"
              strokeWidth={1.5}
            />
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search by title or author…"
              className="w-full rounded-lg border border-border bg-bg-elevated py-2.5 pl-10 pr-4 text-body text-text-primary placeholder-text-subtle outline-none focus:border-accent/50 transition-colors"
            />
          </div>
          <div className="flex flex-wrap gap-2">
            {FILTERS.map((f) => (
              <button
                key={f.id}
                onClick={() => setStatus(f.id)}
                className={cn(
                  "rounded-full px-3 py-1 text-body-sm transition-colors",
                  status === f.id
                    ? "bg-accent text-white"
                    : "bg-bg-elevated text-text-muted hover:text-text-primary border border-border",
                )}
              >
                {f.label}
              </button>
            ))}
          </div>
        </div>

        {/* States */}
        {loading && books.length === 0 ? (
          <SkeletonGrid />
        ) : error ? (
          <div className="flex flex-col items-center justify-center py-20 text-center">
            <p className="text-body text-state-error mb-2">
              Couldn&apos;t load your library.
            </p>
            <p className="text-body-sm text-text-muted">{error}</p>
            <button
              onClick={() => fetchBooks()}
              className="mt-4 rounded-md px-3 py-1.5 text-body-sm bg-bg-elevated text-text-primary border border-border hover:border-accent/40 transition-colors"
            >
              Retry
            </button>
          </div>
        ) : filtered.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-20 text-center">
            <Library className="h-8 w-8 text-text-subtle mb-4" />
            <p className="text-body text-text-muted max-w-sm">
              {books.length === 0
                ? "No textbooks are available yet. Check back soon."
                : "No books match your search."}
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
            {filtered.map((book) => (
              <BookCard key={book.id} book={book} />
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
