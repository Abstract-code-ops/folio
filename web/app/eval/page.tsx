"use client";

// Eval page: what the student asked, what the agent decided, what retrieval
// returned, and what was sent back. Read-only — no model calls, no writes.

import { useCallback, useEffect, useState } from "react";
import { RefreshCw } from "lucide-react";
import { apiClient } from "@/lib/api-client";
import { Loader } from "@/components/ui/loader";
import { cn } from "@/lib/utils";
import type { QaTurn, RetrievedPassage, TurnDiagnostics } from "@/types/qa-turns";

const ACTION_LABEL: Record<TurnDiagnostics["action"], string> = {
  searched_book: "searched the book",
  answered_without_retrieval: "replied without retrieving",
  retrieved: "retrieved (legacy path)",
};

const ACTION_STYLE: Record<TurnDiagnostics["action"], string> = {
  searched_book: "border-accent/40 text-accent",
  answered_without_retrieval: "border-border text-text-subtle",
  retrieved: "border-border text-text-muted",
};

function formatTime(iso: string): string {
  const date = new Date(iso.endsWith("Z") ? iso : `${iso}Z`);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString();
}

function pages(start: number | null, end: number | null): string {
  if (start === null) return "—";
  if (end === null || end === start) return `p. ${start}`;
  return `pp. ${start}–${end}`;
}

function DiagnosticsBlock({ diagnostics }: { diagnostics: TurnDiagnostics }) {
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <span
          className={cn(
            "rounded-full border px-2 py-0.5 text-body-sm",
            ACTION_STYLE[diagnostics.action],
          )}
        >
          {ACTION_LABEL[diagnostics.action]}
        </span>
        <span className="rounded-full border border-border-subtle px-2 py-0.5 text-body-sm text-text-subtle">
          {diagnostics.mode}
        </span>
        <span className="text-body-sm text-text-subtle">
          {diagnostics.retrieved.length} passages · {diagnostics.citations} citations ·{" "}
          {diagnostics.answer_chars} chars
        </span>
      </div>

      {diagnostics.queries.length > 0 && (
        <p className="text-body-sm text-text-muted">
          <span className="text-text-subtle">queries: </span>
          {diagnostics.queries.map((q) => `“${q}”`).join(", ")}
        </p>
      )}

      {diagnostics.error && (
        <p className="rounded-md border border-state-error/40 bg-state-error/10 px-2 py-1 text-body-sm text-state-error">
          {diagnostics.error}
        </p>
      )}

      {diagnostics.retrieved.length > 0 && (
        <div className="space-y-1">
          <p className="text-body-sm text-text-subtle">retrieved</p>
          <ul className="space-y-1">
            {diagnostics.retrieved.map((passage: RetrievedPassage, i) => (
              <li
                key={`${passage.heading}-${passage.chunk_index}-${i}`}
                className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5 rounded-md bg-bg-base px-2 py-1 text-body-sm"
              >
                <span
                  className={cn(
                    "shrink-0 font-mono text-[11px]",
                    passage.role === "match" ? "text-accent" : "text-text-subtle",
                  )}
                >
                  {passage.role}
                </span>
                <span className="min-w-0 flex-1 truncate text-text-primary">
                  {passage.heading}
                </span>
                <span className="shrink-0 text-text-subtle">
                  {pages(passage.page_start, passage.page_end)}
                </span>
                {passage.distance !== null && (
                  <span className="shrink-0 font-mono text-[11px] text-text-subtle">
                    d={passage.distance.toFixed(3)}
                  </span>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function TurnCard({ turn }: { turn: QaTurn }) {
  return (
    <article className="rounded-lg border border-border-subtle bg-bg-surface p-3 sm:p-4">
      <header className="mb-2 flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <span className="min-w-0 truncate text-body-sm text-text-muted">
          {turn.book_title ?? turn.book_id}
        </span>
        <time className="shrink-0 text-body-sm text-text-subtle">
          {formatTime(turn.created_at)}
        </time>
      </header>

      {/* Side by side on desktop, stacked on mobile */}
      <div className="grid gap-3 lg:grid-cols-2">
        <section className="min-w-0">
          <p className="text-body-sm text-text-subtle">asked</p>
          <p className="whitespace-pre-wrap text-body text-text-primary">
            {turn.question}
          </p>

          <p className="mt-3 text-body-sm text-text-subtle">answered</p>
          <p className="whitespace-pre-wrap break-words text-body-sm text-text-muted line-clamp-[12]">
            {turn.answer || "(empty)"}
          </p>

          {turn.sources && turn.sources.length > 0 && (
            <ul className="mt-2 flex flex-wrap gap-1">
              {turn.sources.map((source, i) => (
                <li
                  key={`${source.passage}-${i}`}
                  className="rounded border border-border-subtle px-1.5 py-0.5 text-[11px] text-text-subtle"
                  title={source.excerpt}
                >
                  [{source.passage}] {pages(source.page_start, source.page_end)}
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="min-w-0 border-t border-border-subtle pt-3 lg:border-l lg:border-t-0 lg:pl-3 lg:pt-0">
          <p className="mb-1 text-body-sm text-text-subtle">agent</p>
          {turn.diagnostics ? (
            <DiagnosticsBlock diagnostics={turn.diagnostics} />
          ) : (
            <p className="text-body-sm text-text-subtle">
              No diagnostics — this turn was recorded before they existed.
            </p>
          )}
        </section>
      </div>
    </article>
  );
}

export default function EvalPage() {
  const [turns, setTurns] = useState<QaTurn[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [limit, setLimit] = useState(50);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await apiClient.listQaTurns({ limit });
      setTurns(response.turns);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load turns");
    } finally {
      setLoading(false);
    }
  }, [limit]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className="min-h-dvh bg-bg-base">
      <header className="sticky top-0 z-10 flex flex-wrap items-center gap-2 border-b border-border-subtle bg-bg-surface px-3 py-2 sm:px-4">
        <a
          href="/library"
          className="shrink-0 text-body-sm text-text-muted transition-colors hover:text-text-primary"
        >
          ← Library
        </a>
        <h1 className="font-heading text-body font-semibold text-text-primary">
          Q&amp;A eval
        </h1>
        <span className="text-body-sm text-text-subtle">
          {turns.length} turn{turns.length === 1 ? "" : "s"}
        </span>

        <div className="ml-auto flex items-center gap-2">
          <select
            value={limit}
            onChange={(event) => setLimit(Number(event.target.value))}
            className="rounded-md border border-border-subtle bg-bg-base px-2 py-1 text-body-sm text-text-primary"
            aria-label="How many turns to load"
          >
            <option value={25}>25</option>
            <option value={50}>50</option>
            <option value={100}>100</option>
            <option value={200}>200</option>
          </select>
          <button
            type="button"
            onClick={() => void load()}
            disabled={loading}
            className="flex items-center gap-1.5 rounded-md border border-border-subtle px-2 py-1 text-body-sm text-text-muted transition-colors hover:bg-bg-elevated disabled:opacity-50"
          >
            <RefreshCw className={cn("h-3.5 w-3.5", loading && "animate-spin")} />
            Refresh
          </button>
        </div>
      </header>

      <main className="mx-auto w-full max-w-5xl px-3 py-3 sm:px-4 sm:py-4">
        {loading && turns.length === 0 && (
          <div className="flex justify-center py-10">
            <Loader label="Loading turns…" />
          </div>
        )}

        {error && (
          <p className="rounded-md border border-state-error/40 bg-state-error/10 px-3 py-2 text-body-sm text-state-error">
            {error}
          </p>
        )}

        {!loading && !error && turns.length === 0 && (
          <p className="py-10 text-center text-body text-text-muted">
            No Q&amp;A turns recorded yet. Ask a question in the reader first.
          </p>
        )}

        <div className="space-y-3">
          {turns.map((turn) => (
            <TurnCard key={turn.id} turn={turn} />
          ))}
        </div>
      </main>
    </div>
  );
}
