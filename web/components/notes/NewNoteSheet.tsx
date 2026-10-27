"use client";

import { useCallback, useState } from "react";
import { PenLine, Sparkles, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { apiClient } from "@/lib/api-client";
import { Loader } from "@/components/ui/loader";

/**
 * The two ways to start a note that need no existing text: generate from a topic,
 * or open a blank page and write.
 *
 * Owns its own request state so the notes list stays a list — the alternative was
 * a panel with five modal modes and shared "generating" flags.
 */
export interface NewNoteSheetProps {
  bookId: string;
  onClose: () => void;
  /** A note exists now. `edit` opens it straight into the editor. */
  onCreated: (noteId: string, edit: boolean) => void;
  className?: string;
}

type View = "choose" | "topic";

export function NewNoteSheet({
  bookId,
  onClose,
  onCreated,
  className,
}: NewNoteSheetProps) {
  const [view, setView] = useState<View>("choose");
  const [topic, setTopic] = useState("");
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [cards, setCards] = useState<string[]>([]);

  const writeMyOwn = useCallback(async () => {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      // A blank note: the editor gets a live caret rather than an empty state.
      const note = await apiClient.createNoteDocument({ book_id: bookId });
      onCreated(note.id, true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't create a note");
    } finally {
      setBusy(false);
    }
  }, [bookId, busy, onCreated]);

  const generateFromTopic = useCallback(async () => {
    const value = topic.trim();
    if (!value || busy) return;

    setBusy(true);
    setError(null);
    setCards([]);
    setStatus("Reading the book for this topic…");

    try {
      const stream = await apiClient.generateTopicNotes(bookId, value);
      const reader = stream.getReader();
      let created: string | null = null;

      while (true) {
        const { done, value: next } = await reader.read();
        if (done) break;
        const event = next;
        if (!event) continue;

        switch (event.type) {
          case "card":
            // Show the concepts as they validate, so the wait is legible.
            setCards((seen) => [...seen, event.concept]);
            break;
          case "done":
            created = event.note_id;
            break;
          case "not_covered":
          case "error":
            setError(event.message);
            break;
        }
      }

      if (created) {
        onCreated(created, false);
      }
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Couldn't generate notes",
      );
    } finally {
      setBusy(false);
      setStatus(null);
    }
  }, [bookId, busy, topic, onCreated]);

  return (
    <div
      className={cn(
        "absolute inset-0 z-50 flex items-end sm:items-center justify-center bg-black/60",
        className,
      )}
    >
      <div className="w-full sm:max-w-md bg-bg-surface rounded-t-xl sm:rounded-xl border border-border shadow-xl overflow-hidden">
        <div className="flex items-center justify-between px-4 py-3 border-b border-border-subtle">
          <span className="font-heading text-body-sm font-semibold text-text-primary">
            New note
          </span>
          <button
            onClick={onClose}
            aria-label="Close"
            className="w-7 h-7 flex items-center justify-center rounded-md text-text-subtle hover:text-text-primary hover:bg-bg-elevated transition-colors"
          >
            <X className="h-4 w-4" strokeWidth={1.5} />
          </button>
        </div>

        {view === "choose" ? (
          <div className="p-4 space-y-2">
            <button
              onClick={() => setView("topic")}
              className="flex w-full items-start gap-3 rounded-md border border-border-subtle p-3 text-left hover:bg-bg-elevated transition-colors"
            >
              <Sparkles
                className="h-4 w-4 text-accent mt-0.5 shrink-0"
                strokeWidth={1.5}
              />
              <span className="min-w-0">
                <span className="block text-body-sm text-text-primary">
                  Generate from a topic
                </span>
                <span className="block text-body-sm text-text-subtle">
                  Folio reads the book and cites the pages it used.
                </span>
              </span>
            </button>

            <button
              onClick={writeMyOwn}
              disabled={busy}
              className="flex w-full items-start gap-3 rounded-md border border-border-subtle p-3 text-left hover:bg-bg-elevated transition-colors disabled:opacity-50"
            >
              <PenLine
                className="h-4 w-4 text-text-muted mt-0.5 shrink-0"
                strokeWidth={1.5}
              />
              <span className="min-w-0">
                <span className="block text-body-sm text-text-primary">
                  Write my own
                </span>
                <span className="block text-body-sm text-text-subtle">
                  Opens a blank page with the cursor ready.
                </span>
              </span>
            </button>

            {error && (
              <p className="text-body-sm text-state-error pt-1">{error}</p>
            )}
          </div>
        ) : (
          <div className="p-4 space-y-3">
            <input
              type="text"
              value={topic}
              onChange={(event) => setTopic(event.target.value)}
              placeholder="e.g. B-trees and why databases use them"
              autoFocus
              className="w-full px-3 py-2 rounded-md bg-bg-base border border-border text-body-sm text-text-primary placeholder-text-subtle outline-none focus:border-accent/50 transition-colors"
            />

            {status && (
              <p className="text-body-sm text-text-subtle">{status}</p>
            )}

            {cards.length > 0 && (
              <ul className="space-y-1">
                {cards.map((concept, index) => (
                  <li
                    key={`${concept}-${index}`}
                    className="text-body-sm text-text-primary truncate"
                  >
                    · {concept}
                  </li>
                ))}
              </ul>
            )}

            {error && <p className="text-body-sm text-state-error">{error}</p>}

            <div className="flex justify-end gap-2 pt-1">
              <button
                onClick={() => {
                  setView("choose");
                  setError(null);
                  setCards([]);
                }}
                className="px-3 py-1.5 rounded-md text-body-sm text-text-muted hover:text-text-primary transition-colors"
              >
                Back
              </button>
              <button
                onClick={generateFromTopic}
                disabled={!topic.trim() || busy}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-accent text-white text-body-sm hover:bg-accent-hover transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
              >
                {busy ? (
                  <>
                    <Loader variant="dots" />
                    Generating…
                  </>
                ) : (
                  <>
                    <Sparkles className="h-3.5 w-3.5" strokeWidth={1.5} />
                    Generate notes
                  </>
                )}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
