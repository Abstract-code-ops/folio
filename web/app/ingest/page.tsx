"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import Link from "next/link";
import { BookOpen, Play, Plus, RefreshCw, Trash2 } from "lucide-react";
import { cn } from "@/lib/utils";
import type { BookResponse, IngestionStatus } from "@/types/books";
import {
  createBook,
  deleteBook,
  getIngestStatus,
  listAllBooks,
  triggerIngest,
  updateBookCategory,
  type IngestProgress,
} from "@/lib/admin-api";

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

const POLL_MS = 1500;

export default function IngestPage() {
  const [books, setBooks] = useState<BookResponse[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [progress, setProgress] = useState<IngestProgress | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [loadingList, setLoadingList] = useState(true);

  // Add-book form
  const [title, setTitle] = useState("");
  const [author, setAuthor] = useState("");
  const [storageUrl, setStorageUrl] = useState("");
  const [category, setCategory] = useState("");
  const [adding, setAdding] = useState(false);

  const selected = books.find((b) => b.id === selectedId) ?? null;

  // Category editor for the selected book (assign/change after ingestion).
  const [editCategory, setEditCategory] = useState("");
  useEffect(() => {
    setEditCategory(selected?.category ?? "");
  }, [selected?.id, selected?.category]);

  const loadBooks = useCallback(async (): Promise<BookResponse[]> => {
    setLoadingList(true);
    try {
      const list = await listAllBooks();
      setBooks(list);
      return list;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load books");
      return [];
    } finally {
      setLoadingList(false);
    }
  }, []);

  const select = useCallback((id: string | null) => {
    setSelectedId(id);
    setProgress(null);
    if (typeof window !== "undefined") {
      const url = new URL(window.location.href);
      if (id) url.searchParams.set("book", id);
      else url.searchParams.delete("book");
      window.history.replaceState(null, "", url.toString());
    }
  }, []);

  // Load on mount, then restore the URL book or focus any processing one.
  useEffect(() => {
    void (async () => {
      const list = await loadBooks();
      const fromUrl =
        typeof window !== "undefined"
          ? new URLSearchParams(window.location.search).get("book")
          : null;
      const running = list.find((b) => b.ingestion_status === "processing");
      const initial = (fromUrl && list.some((b) => b.id === fromUrl) ? fromUrl : null)
        ?? running?.id
        ?? null;
      select(initial);
    })();
  }, [loadBooks, select]);

  // Poll the selected book's status. State is server-side, so leaving and
  // returning just re-runs this — the ingest keeps going in the worker thread.
  useEffect(() => {
    if (!selectedId) return;
    let alive = true;
    let timer: ReturnType<typeof setInterval> | null = null;
    let settled = false;
    const stop = () => {
      if (timer) {
        clearInterval(timer);
        timer = null;
      }
    };
    const tick = async () => {
      try {
        const p = await getIngestStatus(selectedId);
        if (!alive) return;
        setProgress(p);
        setError(null);
        if (!p.running) {
          if (!settled) {
            settled = true;
            void loadBooks();
          }
          stop();
        }
      } catch (err) {
        if (alive) setError(err instanceof Error ? err.message : "Status failed");
      }
    };
    void tick();
    timer = setInterval(tick, POLL_MS);
    return () => {
      alive = false;
      stop();
    };
  }, [selectedId, loadBooks]);

  const startIngest = async (force = false) => {
    if (!selectedId) return;
    setBusy(true);
    setError(null);
    try {
      await triggerIngest(selectedId, force);
      setProgress(await getIngestStatus(selectedId));
      await loadBooks();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to start ingest");
    } finally {
      setBusy(false);
    }
  };

  const removeSelected = async () => {
    if (!selectedId || !selected) return;
    if (
      typeof window !== "undefined" &&
      !window.confirm(`Delete "${selected.title}" and all its data? This cannot be undone.`)
    ) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await deleteBook(selectedId);
      select(null);
      await loadBooks();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete book");
    } finally {
      setBusy(false);
    }
  };

  const saveCategory = async () => {
    if (!selectedId) return;
    setBusy(true);
    setError(null);
    try {
      await updateBookCategory(selectedId, editCategory.trim() || null);
      await loadBooks();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update category");
    } finally {
      setBusy(false);
    }
  };

  const addBook = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!title.trim() || !storageUrl.trim()) return;
    setAdding(true);
    setError(null);
    try {
      const created = await createBook({
        title: title.trim(),
        author: author.trim() || "Unknown",
        category: category.trim() || undefined,
        storage_url: storageUrl.trim(),
      });
      setTitle("");
      setAuthor("");
      setStorageUrl("");
      setCategory("");
      await loadBooks();
      select(created.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to add book");
    } finally {
      setAdding(false);
    }
  };

  const total = progress?.sections_total ?? null;
  const done = progress?.sections_done ?? 0;
  const pct = total && total > 0 ? Math.min(100, Math.round((done / total) * 100)) : null;
  const running = progress?.running ?? false;
  const completed = selected?.ingestion_status === "completed";
  const failed = selected?.ingestion_status === "failed";

  return (
    <div className="min-h-dvh bg-bg-base">
      <header className="sticky top-0 z-10 flex flex-wrap items-center gap-2 border-b border-border-subtle bg-bg-surface px-3 py-2 sm:px-4">
        <Link
          href="/admin"
          className="shrink-0 text-body-sm text-text-muted transition-colors hover:text-text-primary"
        >
          ← Admin
        </Link>
        <h1 className="font-heading text-body font-semibold text-text-primary">
          Ingest books
        </h1>
        <button
          type="button"
          onClick={() => void loadBooks()}
          disabled={loadingList}
          className="ml-auto flex items-center gap-1.5 rounded-md border border-border-subtle px-2 py-1 text-body-sm text-text-muted transition-colors hover:bg-bg-elevated disabled:opacity-50"
        >
          <RefreshCw className={cn("h-3.5 w-3.5", loadingList && "animate-spin")} />
          Refresh
        </button>
      </header>

      <main className="mx-auto grid w-full max-w-6xl gap-4 px-3 py-4 sm:px-4 lg:grid-cols-[minmax(0,320px)_minmax(0,1fr)]">
        {/* Book list */}
        <section className="min-w-0">
          <h2 className="mb-2 text-body-sm font-medium text-text-subtle">
            {books.length} book{books.length === 1 ? "" : "s"}
          </h2>
          <ul className="space-y-1">
            {books.map((book) => {
              const isActive = book.id === selectedId;
              return (
                <li key={book.id}>
                  <button
                    type="button"
                    onClick={() => select(book.id)}
                    className={cn(
                      "flex w-full items-center gap-2 rounded-lg border px-3 py-2 text-left transition-colors",
                      isActive
                        ? "border-accent/40 bg-accent/10"
                        : "border-border-subtle bg-bg-surface hover:bg-bg-elevated",
                    )}
                  >
                    <span className={cn("h-2 w-2 shrink-0 rounded-full", STATUS_DOT[book.ingestion_status])} />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-body-sm text-text-primary">
                        {book.title}
                      </span>
                      <span className="block truncate text-[11px] text-text-subtle">
                        {book.author} · {STATUS_LABEL[book.ingestion_status]}
                        {book.section_count ? ` · ${book.section_count} sections` : ""}
                      </span>
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>

          {/* Add a book */}
          <details className="mt-4 rounded-lg border border-border-subtle bg-bg-surface">
            <summary className="flex cursor-pointer items-center gap-1.5 px-3 py-2 text-body-sm text-text-muted">
              <Plus className="h-3.5 w-3.5" />
              Add a book
            </summary>
            <form onSubmit={addBook} className="space-y-2 px-3 pb-3 pt-1">
              <input
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="Title"
                className="w-full rounded-md border border-border-subtle bg-bg-base px-2 py-1.5 text-body-sm text-text-primary"
              />
              <input
                value={author}
                onChange={(e) => setAuthor(e.target.value)}
                placeholder="Author"
                className="w-full rounded-md border border-border-subtle bg-bg-base px-2 py-1.5 text-body-sm text-text-primary"
              />
              <input
                value={storageUrl}
                onChange={(e) => setStorageUrl(e.target.value)}
                placeholder="PDF public URL (storage_url)"
                className="w-full rounded-md border border-border-subtle bg-bg-base px-2 py-1.5 text-body-sm text-text-primary"
              />
              <input
                value={category}
                onChange={(e) => setCategory(e.target.value)}
                list="category-options"
                placeholder="Category (e.g. Mathematics)"
                className="w-full rounded-md border border-border-subtle bg-bg-base px-2 py-1.5 text-body-sm text-text-primary"
              />
              <datalist id="category-options">
                {Array.from(
                  new Set(
                    books
                      .map((b) => b.category)
                      .filter((c): c is string => Boolean(c)),
                  ),
                ).map((c) => (
                  <option key={c} value={c} />
                ))}
              </datalist>
              <button
                type="submit"
                disabled={adding || !title.trim() || !storageUrl.trim()}
                className="flex w-full items-center justify-center gap-1.5 rounded-md bg-accent px-3 py-1.5 text-body-sm font-medium text-bg-base transition-opacity hover:opacity-90 disabled:opacity-50"
              >
                {adding ? "Adding…" : "Add book"}
              </button>
            </form>
          </details>
        </section>

        {/* Detail / progress */}
        <section className="min-w-0">
          {error && (
            <p className="mb-3 rounded-md border border-state-error/40 bg-state-error/10 px-3 py-2 text-body-sm text-state-error">
              {error}
            </p>
          )}

          {!selected && (
            <div className="flex h-48 items-center justify-center rounded-xl border border-dashed border-border-subtle text-body text-text-subtle">
              <BookOpen className="mr-2 h-5 w-5" />
              Select a book, or add one.
            </div>
          )}

          {selected && (
            <div className="space-y-4 rounded-xl border border-border-subtle bg-bg-surface p-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <h2 className="truncate font-heading text-body font-semibold text-text-primary">
                    {selected.title}
                  </h2>
                  <p className="truncate text-body-sm text-text-subtle">{selected.author}</p>
                </div>
                <span className="flex items-center gap-1.5 rounded-full border border-border-subtle px-2 py-0.5 text-body-sm text-text-muted">
                  <span className={cn("h-2 w-2 rounded-full", STATUS_DOT[progress?.status ?? selected.ingestion_status])} />
                  {STATUS_LABEL[progress?.status ?? selected.ingestion_status]}
                </span>
              </div>

              <p className="truncate rounded-md bg-bg-base px-2 py-1 font-mono text-[11px] text-text-subtle" title={selected.storage_url}>
                {selected.storage_url}
              </p>

              {/* Assign/change the category of an already-ingested book */}
              <div className="flex flex-wrap items-center gap-2">
                <label className="text-body-sm text-text-subtle" htmlFor="edit-category">
                  Category
                </label>
                <input
                  id="edit-category"
                  value={editCategory}
                  onChange={(e) => setEditCategory(e.target.value)}
                  list="edit-category-options"
                  placeholder="e.g. Mathematics"
                  className="min-w-0 flex-1 rounded-md border border-border-subtle bg-bg-base px-2 py-1.5 text-body-sm text-text-primary"
                />
                <datalist id="edit-category-options">
                  {Array.from(
                    new Set(
                      books
                        .map((b) => b.category)
                        .filter((c): c is string => Boolean(c)),
                    ),
                  ).map((c) => (
                    <option key={c} value={c} />
                  ))}
                </datalist>
                <button
                  type="button"
                  onClick={() => void saveCategory()}
                  disabled={busy || editCategory.trim() === (selected.category ?? "")}
                  className="rounded-md border border-accent/40 px-3 py-1.5 text-body-sm text-accent transition-colors hover:bg-accent/10 disabled:opacity-50"
                >
                  Save category
                </button>
              </div>

              {/* Progress bar */}
              <div>
                <div className="mb-1 flex items-center justify-between text-body-sm text-text-subtle">
                  <span>
                    {done}
                    {total ? ` / ${total}` : ""} sections
                  </span>
                  <span>{pct !== null ? `${pct}%` : running ? "working…" : ""}</span>
                </div>
                <div className="h-2 w-full overflow-hidden rounded-full bg-bg-base">
                  <div
                    className={cn(
                      "h-full rounded-full bg-accent transition-[width] duration-500",
                      pct === null && running && "animate-pulse",
                    )}
                    style={pct !== null ? { width: `${pct}%` } : { width: running ? "35%" : "0%" }}
                  />
                </div>
              </div>

              {/* Live console */}
              <div className="rounded-lg border border-border-subtle bg-bg-base p-3 font-mono text-[12px] leading-relaxed text-text-muted">
                {progress ? (
                  <div className="space-y-0.5">
                    <div>
                      <span className="text-text-subtle">status </span>
                      {progress.status}
                    </div>
                    <div>
                      <span className="text-text-subtle">sections </span>
                      {progress.sections_done}
                      {progress.sections_total ? ` / ${progress.sections_total}` : ""}
                    </div>
                    <div>
                      <span className="text-text-subtle">chunks </span>
                      {progress.chunks}
                    </div>
                    <div>
                      <span className="text-text-subtle">tables </span>
                      {progress.tables}
                    </div>
                    <div>
                      <span className="text-text-subtle">figures </span>
                      {progress.figures}
                      {progress.figures === 0 ? " (none detected)" : ""}
                    </div>
                    <div>
                      <span className="text-text-subtle">words </span>
                      {progress.word_count ?? "—"}
                    </div>
                    <div className={running ? "text-state-warning" : "text-text-subtle"}>
                      {running ? "→ ingesting…" : "→ idle"}
                    </div>
                  </div>
                ) : (
                  <span className="text-text-subtle">Loading status…</span>
                )}
              </div>

              {completed ? (
                <div className="flex flex-wrap items-center gap-2">
                  <button
                    type="button"
                    onClick={() => void startIngest(true)}
                    disabled={busy || running}
                    className="flex items-center justify-center gap-2 rounded-md border border-accent/50 bg-accent/10 px-4 py-2 text-body-sm font-medium text-accent transition-colors hover:bg-accent/15 disabled:opacity-50"
                  >
                    <RefreshCw className={cn("h-4 w-4", busy && "animate-spin")} />
                    {busy ? "Starting…" : running ? "Re-ingesting…" : "Re-ingest (force)"}
                  </button>
                  <span className="text-body-sm text-text-subtle">
                    Re-runs to backfill tables/figures (idempotent).
                  </span>
                </div>
              ) : (
                <button
                  type="button"
                  onClick={() => void startIngest(false)}
                  disabled={busy || running || selected.ingestion_status === "processing"}
                  className="flex items-center justify-center gap-2 rounded-md bg-accent px-4 py-2 text-body-sm font-medium text-bg-base transition-opacity hover:opacity-90 disabled:opacity-50"
                >
                  <Play className="h-4 w-4" />
                  {running || selected.ingestion_status === "processing"
                    ? "Ingesting…"
                    : busy
                      ? "Starting…"
                      : "Start ingestion"}
                </button>
              )}

              {failed && (
                <p className="text-body-sm text-state-error">
                  Previous run failed — check `docker compose logs api`, then Start again.
                </p>
              )}

              <div className="flex items-center justify-between border-t border-border-subtle pt-3">
                <span className="text-body-sm text-text-subtle">Danger zone</span>
                <button
                  type="button"
                  onClick={() => void removeSelected()}
                  disabled={busy || running}
                  className="flex items-center gap-1.5 rounded-md border border-state-error/40 px-3 py-1.5 text-body-sm text-state-error transition-colors hover:bg-state-error/10 disabled:opacity-50"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                  Delete book
                </button>
              </div>
            </div>
          )}
        </section>
      </main>
    </div>
  );
}
