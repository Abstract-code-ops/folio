"use client";

import { useMemo, useState } from "react";
import {
  ChevronRight,
  Download,
  FileText,
  NotebookPen,
  PenLine,
  Sparkles,
  Upload,
} from "lucide-react";
import { cn } from "@/lib/utils";
import {
  citedSectionIds,
  useNotesNav,
  useNotesStore,
} from "@/lib/notes-store";
import { importNotesForBook } from "@/lib/sync";
import { NewNoteMenu } from "./NewNoteMenu";
import { NoteEditor } from "./NoteEditor";
import { NoteView } from "./NoteView";

export interface NotesPanelProps {
  bookId: string;
  /** The section the reader is on, resolved by the reader from the book. */
  sectionId?: string;
  /** Its heading, used as the label above the backlinks. */
  sectionHeading?: string;
  /** Jump the reader to a cited page — the same contract the chat panel uses. */
  onCitationClick?: (target: { page: number; text: string }) => void;
  className?: string;
}

export function NotesPanel({
  bookId,
  sectionId,
  sectionHeading,
  onCitationClick,
  className,
}: NotesPanelProps) {
  // Notes are local (localStorage), so the list is a derivation of the store —
  // no request, no cache, no loading state.
  const notes = useNotesStore((s) => s.notes);
  const list = useMemo(
    () =>
      Object.values(notes)
        .filter((note) => note.bookId === bookId)
        .sort((a, b) => b.updatedAt - a.updatedAt),
    [notes, bookId],
  );

  // Which note the panel shows lives in a store, not local state, so it survives
  // the panel unmounting (desktop collapse or a mobile sheet closing). In memory
  // only, so a reload starts on the list.
  const openNoteId = useNotesNav((s) => s.byBook[bookId]?.openNoteId ?? null);
  const editing = useNotesNav((s) => s.byBook[bookId]?.editing ?? false);
  const openNote = useNotesNav((s) => s.open);
  const setEditing = useNotesNav((s) => s.setEditing);

  // Backlinks: a local filter over the cited section ids, so flipping pages
  // never touches the network.
  const backlinks = useMemo(() => {
    if (!sectionId) return null;
    return list.filter((note) => citedSectionIds(note).includes(sectionId)).slice(0, 5);
  }, [list, sectionId]);

  const handleNoteCreated = (noteId: string | null, edit: boolean) => {
    openNote(bookId, noteId);
    if (edit) setEditing(bookId, true);
  };

  const [importing, setImporting] = useState(false);

  const downloadNotes = () => {
    const json = useNotesStore.getState().exportNotes();
    const blob = new Blob([json], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "folio-notes.json";
    anchor.click();
    URL.revokeObjectURL(url);
  };

  const importServerNotes = async () => {
    if (importing) return;
    setImporting(true);
    try {
      await importNotesForBook(bookId, { force: true });
    } finally {
      setImporting(false);
    }
  };

  function formatRelative(ms: number): string {
    const formatter = new Intl.RelativeTimeFormat("en", { numeric: "auto" });
    const minutes = Math.round((ms - Date.now()) / 60000);
    if (Math.abs(minutes) < 60) return formatter.format(minutes, "minute");
    const hours = Math.round(minutes / 60);
    if (Math.abs(hours) < 24) return formatter.format(hours, "hour");
    const days = Math.round(hours / 24);
    if (Math.abs(days) < 30) return formatter.format(days, "day");
    return formatter.format(Math.round(days / 30), "month");
  }

  // One note at a time: the list is the index, the note is the page.
  if (editing) {
    return (
      <NoteEditor
        bookId={bookId}
        noteId={openNoteId}
        onDone={() => setEditing(bookId, false)}
        className={className}
      />
    );
  }

  if (openNoteId) {
    return (
      <NoteView
        noteId={openNoteId}
        onBack={() => openNote(bookId, null)}
        onEdit={() => setEditing(bookId, true)}
        onCitationClick={onCitationClick}
        className={className}
      />
    );
  }

  return (
    <div className={cn("flex min-h-0 flex-1 flex-col", className)}>
      {/* Header */}
      <div className="shrink-0 border-b border-border-subtle px-5 py-4 lg:px-6">
        <h2 className="font-heading text-body font-semibold text-text-primary">
          Notes
        </h2>
        <p className="mt-1 text-body-sm text-text-muted">
          Notes you generate or write, kept in this browser.
        </p>
        <NewNoteMenu bookId={bookId} onCreated={handleNoteCreated} className="mt-3" />
        <div className="mt-2 flex items-center gap-1">
          <button
            onClick={downloadNotes}
            className="inline-flex min-h-11 items-center gap-1.5 rounded-md px-2 py-1 text-body-sm text-text-muted transition-colors hover:bg-bg-elevated hover:text-text-primary sm:min-h-0"
          >
            <Download className="h-3.5 w-3.5" strokeWidth={1.5} />
            Download
          </button>
          <button
            onClick={importServerNotes}
            disabled={importing}
            className="inline-flex min-h-11 items-center gap-1.5 rounded-md px-2 py-1 text-body-sm text-text-muted transition-colors hover:bg-bg-elevated hover:text-text-primary disabled:opacity-50 sm:min-h-0"
          >
            <Upload className="h-3.5 w-3.5" strokeWidth={1.5} />
            {importing ? "Importing…" : "Import"}
          </button>
        </div>
      </div>

      {/* Note list — scrollable */}
      <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain">
        {sectionHeading && backlinks && backlinks.length > 0 && (
          <div className="border-b border-border-subtle bg-bg-elevated/40 px-5 py-4 lg:px-6">
            <p className="text-body-sm text-text-subtle">On this section</p>
            <p className="text-body-sm text-text-primary truncate">
              {sectionHeading}
            </p>
            <div className="mt-2 space-y-1">
              {backlinks.map((note) => (
                <button
                  key={note.id}
                  onClick={() => openNote(bookId, note.id)}
                  className="flex w-full items-center gap-1.5 rounded px-2 py-1.5 text-left text-body-sm text-text-primary hover:bg-bg-base transition-colors"
                >
                  <FileText
                    className="h-3.5 w-3.5 shrink-0 text-text-subtle"
                    strokeWidth={1.5}
                  />
                  <span className="truncate">{note.title ?? "Untitled note"}</span>
                </button>
              ))}
            </div>
          </div>
        )}

        {list.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12 px-4 text-center">
            <FileText className="h-8 w-8 text-text-subtle mb-3" />
            <p className="text-body text-text-muted mb-1">No notes yet</p>
            <p className="text-body-sm text-text-subtle">
              Start a note to keep what you learn from this book.
            </p>
          </div>
        ) : (
          <div className="divide-y divide-border-subtle">
            {list.map((note) => {
              const sections = citedSectionIds(note).length;
              const generated = note.source === "ai_generated";
              return (
                <button
                  key={note.id}
                  onClick={() => openNote(bookId, note.id)}
                  className="group flex min-h-14 w-full items-center gap-3 px-5 py-3.5 text-left transition-colors hover:bg-bg-elevated/50 lg:px-6"
                >
                  {/* Origin, so the list says at a glance how the note was made. */}
                  <span className="shrink-0 text-text-muted">
                    {generated ? (
                      <Sparkles className="h-4 w-4" strokeWidth={1.5} />
                    ) : (
                      <PenLine className="h-4 w-4" strokeWidth={1.5} />
                    )}
                    <span className="sr-only">
                      {generated ? "Generated by AI" : "Written by you"}
                    </span>
                  </span>

                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-body font-medium text-text-primary">
                      {note.title ?? "Untitled note"}
                    </span>
                    <span className="block truncate text-body-sm text-text-subtle">
                      {sections > 0
                        ? `${sections} ${sections === 1 ? "section" : "sections"} · `
                        : ""}
                      {formatRelative(note.updatedAt)}
                    </span>
                  </span>

                  {/* A page-with-pen that becomes an arrow on hover. */}
                  <span className="relative h-4 w-4 shrink-0 text-text-subtle">
                    <NotebookPen
                      className="absolute inset-0 h-4 w-4 transition-opacity group-hover:opacity-0"
                      strokeWidth={1.5}
                    />
                    <ChevronRight
                      className="absolute inset-0 h-4 w-4 opacity-0 transition-opacity group-hover:opacity-100"
                      strokeWidth={1.5}
                    />
                  </span>
                </button>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
