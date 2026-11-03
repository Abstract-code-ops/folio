"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  ChevronDown,
  ChevronRight,
  Layers,
  PenLine,
  Sparkles,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { apiClient } from "@/lib/api-client";
import { isAuthed } from "@/lib/guest";
import { notifyUnauthorized } from "@/lib/notify";
import { Loader } from "@/components/ui/loader";
import { makeLocalNote, useNotesStore, type LocalBlock } from "@/lib/notes-store";
import { startTopicNoteGeneration } from "@/lib/note-generation";
import { startChapterNoteGeneration } from "@/lib/note-generation";
import type { NoteTopicEvent } from "@/types/notes";

/**
 * One entry point for starting a note.
 *
 * A dropdown rather than a full-screen sheet: the choices are short, and an
 * overlay hid the list the student was looking at. Topic and chapter both expand
 * their fields in place, so nothing is covered; "Write my own" is the only one
 * that leaves the menu, which is why it is the only one with an arrow.
 */
/** Map the `done` event's server-built blocks into local blocks. */
function blocksFromDone(
  done: Extract<NoteTopicEvent, { type: "done" }>,
): LocalBlock[] {
  return done.blocks.map((block) => ({
    id: crypto.randomUUID(),
    kind: block.kind,
    text: block.text,
    origin: block.origin ?? "ai",
    links: (block.links ?? []).map((link) => ({
      id: crypto.randomUUID(),
      section_id: link.section_id ?? null,
      anchor_heading_path: link.anchor_heading_path,
      page_start: link.page_start,
      page_end: link.page_end,
      excerpt: link.excerpt,
      status: link.status ?? "accepted",
      origin: link.origin,
    })),
  }));
}

export interface NewNoteMenuProps {
  bookId: string;
  /** A note (or a new draft, `null`) exists now. `edit` opens it into the editor. */
  onCreated: (noteId: string | null, edit: boolean) => void;
  /** Chapter generation changes nothing in the list, but the panel refreshes. */
  onRefresh?: () => void;
  className?: string;
}

type View = "menu" | "topic" | "chapter";

export function NewNoteMenu({
  bookId,
  onCreated,
  onRefresh,
  className,
}: NewNoteMenuProps) {
  const [open, setOpen] = useState(false);
  const [view, setView] = useState<View>("menu");
  const [topic, setTopic] = useState("");
  const [chapterStart, setChapterStart] = useState(0);
  const [chapterEnd, setChapterEnd] = useState(0);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [cards, setCards] = useState<string[]>([]);
  const wrapper = useRef<HTMLDivElement>(null);

  const close = useCallback(() => {
    setOpen(false);
    setView("menu");
    setError(null);
    setCards([]);
    setStatus(null);
  }, []);

  useEffect(() => {
    if (!open) return;

    const onPointerDown = (event: MouseEvent) => {
      if (wrapper.current && !wrapper.current.contains(event.target as Node)) {
        close();
      }
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") close();
    };

    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open, close]);

  const writeMyOwn = useCallback(() => {
    if (busy) return;
    close();
    onCreated(null, true);
  }, [busy, close, onCreated]);

  const generateFromTopic = useCallback(() => {
    if (!isAuthed()) {
      notifyUnauthorized();
      close();
      return;
    }
    const value = topic.trim();
    if (!value) return;
    // Runs in the background: a placeholder note appears immediately and
    // finishes on its own even if the student leaves this panel.
    startTopicNoteGeneration(bookId, value);
    setTopic("");
    close();
  }, [bookId, topic, close]);

  const generateChapterRange = useCallback(() => {
    if (!isAuthed()) {
      notifyUnauthorized();
      close();
      return;
    }
    if (chapterEnd < chapterStart) return;
    // Runs in the background: a placeholder note appears in the list and
    // finishes on its own even if the student leaves.
    startChapterNoteGeneration(bookId, chapterStart, chapterEnd);
    close();
    setChapterStart(0);
    setChapterEnd(0);
    onRefresh?.();
  }, [bookId, chapterStart, chapterEnd, close, onRefresh]);

  const item = (
    icon: React.ReactNode,
    label: string,
    hint: string,
    onClick: () => void,
    arrow = false,
  ) => (
    <button
      onClick={onClick}
      disabled={busy}
      className="flex w-full items-center gap-3 rounded-md px-3 py-2.5 text-left transition-colors hover:bg-bg-elevated disabled:opacity-50"
    >
      <span className="shrink-0 text-text-muted">{icon}</span>
      <span className="min-w-0 flex-1">
        <span className="block text-body-sm text-text-primary">{label}</span>
        <span className="block text-body-sm text-text-subtle">{hint}</span>
      </span>
      {arrow && (
        <ChevronRight
          className="h-4 w-4 shrink-0 text-text-subtle"
          strokeWidth={1.5}
        />
      )}
    </button>
  );

  const field =
    "w-full rounded-md border border-border bg-bg-base px-3 py-2 text-body-sm text-text-primary placeholder-text-subtle outline-none transition-colors focus:border-accent/50";

  return (
    <div ref={wrapper} className={cn("relative", className)}>
      <button
        onClick={() => (open ? close() : setOpen(true))}
        aria-expanded={open}
        aria-haspopup="menu"
        className="flex min-h-11 w-full items-center justify-center gap-1.5 rounded-md bg-accent px-4 py-2 text-body-sm text-white transition-colors hover:bg-accent-hover sm:min-h-0"
      >
        <PenLine className="h-3.5 w-3.5" strokeWidth={1.5} />
        New note
        <ChevronDown
          className={cn("h-3.5 w-3.5 transition-transform", open && "rotate-180")}
          strokeWidth={1.5}
        />
      </button>

      {open && (
        <div
          role="menu"
          className="absolute left-0 right-0 top-full z-40 mt-1 rounded-lg border border-border bg-bg-surface p-1 shadow-xl"
        >
          {view === "menu" && (
            <>
              {item(
                <Sparkles className="h-4 w-4" strokeWidth={1.5} />,
                "From a topic",
                "Folio reads the book and cites the pages it used.",
                () => setView("topic"),
              )}
              {item(
                <Layers className="h-4 w-4" strokeWidth={1.5} />,
                "A chapter range",
                "Section-by-section notes for a span of chapters.",
                () => setView("chapter"),
              )}
              {item(
                <PenLine className="h-4 w-4" strokeWidth={1.5} />,
                "Write my own",
                "Opens a blank page with the cursor ready.",
                writeMyOwn,
                true,
              )}
              {error && (
                <p className="px-3 pb-2 text-body-sm text-state-error">{error}</p>
              )}
            </>
          )}

          {view === "topic" && (
            <div className="space-y-2 p-2">
              <input
                type="text"
                value={topic}
                onChange={(event) => setTopic(event.target.value)}
                placeholder="e.g. B-trees and why databases use them"
                autoFocus
                className={field}
              />

              {status && <p className="text-body-sm text-text-subtle">{status}</p>}

              {cards.length > 0 && (
                <ul className="space-y-1">
                  {cards.map((concept, index) => (
                    <li
                      key={`${concept}-${index}`}
                      className="truncate text-body-sm text-text-primary"
                    >
                      · {concept}
                    </li>
                  ))}
                </ul>
              )}

              {error && <p className="text-body-sm text-state-error">{error}</p>}

              <div className="flex justify-between gap-2 pt-1">
                <button
                  onClick={() => {
                    setView("menu");
                    setError(null);
                    setCards([]);
                  }}
                  className="px-3 py-1.5 text-body-sm text-text-muted transition-colors hover:text-text-primary"
                >
                  Back
                </button>
                <button
                  onClick={generateFromTopic}
                  disabled={!topic.trim()}
                  className="flex min-h-11 items-center gap-1.5 rounded-md bg-accent px-3 py-1.5 text-body-sm text-white transition-colors hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-30 sm:min-h-0"
                >
                  Generate in background
                </button>
              </div>
            </div>
          )}

          {view === "chapter" && (
            <div className="space-y-2 p-2">
              <div className="flex items-center gap-2">
                <label className="flex-1">
                  <span className="mb-1 block text-body-sm text-text-subtle">
                    From chapter
                  </span>
                  <input
                    type="number"
                    min={0}
                    value={chapterStart}
                    onChange={(event) =>
                      setChapterStart(parseInt(event.target.value, 10) || 0)
                    }
                    className={field}
                  />
                </label>
                <label className="flex-1">
                  <span className="mb-1 block text-body-sm text-text-subtle">
                    To chapter
                  </span>
                  <input
                    type="number"
                    min={0}
                    value={chapterEnd}
                    onChange={(event) =>
                      setChapterEnd(parseInt(event.target.value, 10) || 0)
                    }
                    className={field}
                  />
                </label>
              </div>

              {status && <p className="text-body-sm text-text-subtle">{status}</p>}
              {error && <p className="text-body-sm text-state-error">{error}</p>}

              <div className="flex justify-between gap-2 pt-1">
                <button
                  onClick={() => {
                    setView("menu");
                    setError(null);
                  }}
                  className="px-3 py-1.5 text-body-sm text-text-muted transition-colors hover:text-text-primary"
                >
                  Back
                </button>
                <button
                  onClick={generateChapterRange}
                  disabled={chapterEnd < chapterStart}
                  className="flex min-h-11 items-center gap-1.5 rounded-md bg-accent px-3 py-1.5 text-body-sm text-white transition-colors hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-30 sm:min-h-0"
                >
                  Generate in background
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
