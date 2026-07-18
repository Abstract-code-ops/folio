"use client";

import { useEffect, useState } from "react";
import { BookOpen, Library, ChevronRight, Loader2 } from "lucide-react";
import Link from "next/link";
import { apiClient } from "@/lib/api-client";
import type { IngestionStatus, BookResponse } from "@/types/books";

const STATUS_LABEL: Record<IngestionStatus, string> = {
  not_started: "Not started",
  processing: "Processing…",
  completed: "Ready",
  failed: "Failed",
};

const STATUS_COLOR: Record<IngestionStatus, string> = {
  not_started: "text-text-subtle",
  processing: "text-state-warning",
  completed: "text-state-success",
  failed: "text-state-error",
};

function BookCard({ id, title, author, ingestion_status, section_count }: BookResponse) {
  return (
    <Link
      href={`/reader?id=${id}`}
      className="group block rounded-xl bg-bg-elevated border border-border p-5 hover:border-accent/40 transition-colors"
    >
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1 min-w-0">
          <h3 className="font-heading text-h6 text-text-primary truncate">
            {title}
          </h3>
          <p className="text-body-sm text-text-muted mt-1">{author}</p>
          <div className="flex items-center gap-3 mt-3">
            <span className={`text-body-sm font-medium ${STATUS_COLOR[ingestion_status]}`}>
              {STATUS_LABEL[ingestion_status]}
            </span>
            {section_count !== null && (
              <span className="text-body-sm text-text-subtle">
                {section_count} sections
              </span>
            )}
          </div>
        </div>
        <ChevronRight className="h-5 w-5 text-text-subtle group-hover:text-accent transition-colors shrink-0 mt-1" />
      </div>
    </Link>
  );
}

export default function LibraryPage() {
  const [books, setBooks] = useState<BookResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    apiClient
      .listBooks()
      .then((res) => {
        if (!cancelled) {
          setBooks(res.books);
          setLoading(false);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load books");
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="min-h-screen bg-bg-base">
      {/* Header */}
      <header className="flex items-center justify-between px-6 h-14 border-b border-border-subtle">
        <div className="flex items-center gap-3">
          <BookOpen className="h-5 w-5 text-accent" />
          <span className="font-heading text-h6 text-text-primary">Folio</span>
        </div>
        <button className="text-body-sm text-text-muted hover:text-text-primary transition-colors">
          Sign in
        </button>
      </header>

      {/* Library content */}
      <main className="max-w-5xl mx-auto px-6 py-10">
        <div className="flex items-center gap-2 mb-8">
          <Library className="h-5 w-5 text-text-muted" />
          <h1 className="font-heading text-h3 text-text-primary">Your library</h1>
        </div>

        {loading ? (
          <div className="flex items-center justify-center py-20">
            <Loader2 className="h-6 w-6 text-text-muted animate-spin" />
          </div>
        ) : error ? (
          <div className="flex flex-col items-center justify-center py-20 text-center">
            <p className="text-body text-state-error mb-2">Couldn&apos;t load your library.</p>
            <p className="text-body-sm text-text-muted">{error}</p>
          </div>
        ) : books.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-20 text-center">
            <Library className="h-8 w-8 text-text-subtle mb-4" />
            <p className="text-body text-text-muted max-w-sm">
              Your library is empty. Browse open-access books to get started.
            </p>
          </div>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {books.map((book) => (
              <BookCard key={book.id} {...book} />
            ))}
          </div>
        )}

        {/* Open-access section — same books shown as the library catalog */}
        {!loading && !error && books.length > 0 && (
          <section className="mt-16">
            <h2 className="font-heading text-h5 text-text-primary mb-4">
              Open-access library
            </h2>
            <p className="text-body text-text-muted mb-6">
              Pre-loaded CS and software engineering textbooks available to everyone.
            </p>
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {books.map((book) => (
                <BookCard key={`open-${book.id}`} {...book} />
              ))}
            </div>
          </section>
        )}
      </main>
    </div>
  );
}
