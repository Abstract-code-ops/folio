"use client";

import { useState, useEffect, useCallback, useMemo } from "react";
import {
  FileText,
  Plus,
  ChevronRight,
  Sparkles,
  X,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { apiClient } from "@/lib/api-client";
import { isFresh, useNotesCache } from "@/lib/notes-store";
import { Loader } from "@/components/ui/loader";
import { NewNoteSheet } from "./NewNoteSheet";
import { NoteEditor } from "./NoteEditor";
import { NoteView } from "./NoteView";
import type {
  NoteSessionResponse,
  NoteSessionListResponse,
  GeneratedSectionNotes,
} from "@/types/notes";
// ── Component ────────────────────────────────────────────────

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

type ModalMode = "paste" | "ai_generate" | null;

export function NotesPanel({
  bookId,
  sectionId,
  sectionHeading,
  onCitationClick,
  className,
}: NotesPanelProps) {
  const [sessions, setSessions] = useState<NoteSessionResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [openNoteId, setOpenNoteId] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [showSheet, setShowSheet] = useState(false);
  const [modalMode, setModalMode] = useState<ModalMode>(null);
  const [submitting, setSubmitting] = useState(false);

  // Paste note form
  const [pasteTitle, setPasteTitle] = useState("");
  const [pasteText, setPasteText] = useState("");

  // AI generate form
  const [chapterStart, setChapterStart] = useState(0);
  const [chapterEnd, setChapterEnd] = useState(0);
  const [generating, setGenerating] = useState(false);

  // ── Cache: the list paints from memory and refreshes in the background ──
  const saveCached = useNotesCache((state) => state.save);
  const touchCached = useNotesCache((state) => state.touch);

  const fetchSessions = useCallback(async () => {
    try {
      const data = await apiClient.listNoteSessions(bookId, { limit: 50 });
      setSessions(data.sessions);
      saveCached(bookId, data.sessions, data.total);
      setError(null);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to load note sessions",
      );
    } finally {
      setLoading(false);
    }
  }, [bookId, saveCached]);

  // First open of a book paints from the cache when there is one, and only
  // talks to the server when the entry is missing or past its TTL. Without
  // this the panel re-queried on every tab switch, at ~1s per round trip.
  useEffect(() => {
    const entry = useNotesCache.getState().byBook[bookId];
    if (entry) {
      setSessions(entry.sessions);
      setLoading(false);
    }
    if (isFresh(entry)) return;
    void fetchSessions();
  }, [bookId, fetchSessions]);

  // ── Backlinks, computed from the cached list ───────────────
  // Each note summary carries the sections it cites, so this is a filter, not a
  // request: flipping pages must never touch the database.
  const backlinks = useMemo(() => {
    if (!sectionId) return null;
    return sessions
      .filter((note) => (note.section_ids ?? []).includes(sectionId))
      .slice(0, 5);
  }, [sessions, sectionId]);

  // ── Submit pasted notes ─────────────────────────────────────
  const handlePasteSubmit = useCallback(async () => {
    if (!pasteText.trim() || submitting) return;
    setSubmitting(true);
    try {
      await apiClient.createNoteSession({
        book_id: bookId,
        raw_text: pasteText,
        source: "pasted",
        title: pasteTitle.trim() || undefined,
      });
      setPasteTitle("");
      setPasteText("");
      setModalMode(null);
      await fetchSessions();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to submit notes",
      );
    } finally {
      setSubmitting(false);
    }
  }, [pasteText, pasteTitle, submitting, bookId, fetchSessions]);

  // ── Trigger AI generation ───────────────────────────────────
  const handleAiGenerate = useCallback(async () => {
    if (chapterEnd < chapterStart || generating) return;
    setGenerating(true);
    try {
      const stream = await apiClient.generateNotes(
        bookId,
        chapterStart,
        chapterEnd,
      );
      const reader = stream.getReader();

      while (true) {
        const { done } = await reader.read();
        if (done) break;
        // We consume the stream to trigger the generation;
        // each section completion already emits a coverage event on the backend
      }

      setModalMode(null);
      setChapterStart(0);
      setChapterEnd(0);
      await fetchSessions();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to generate notes",
      );
    } finally {
      setGenerating(false);
    }
  }, [chapterStart, chapterEnd, generating, bookId, fetchSessions]);

  // ── Format date ─────────────────────────────────────────────
  function formatDate(iso: string): string {
    const d = new Date(iso);
    return d.toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  }

  // One note at a time: the list is the index, the note is the page.
  if (openNoteId && editing) {
    return (
      <NoteEditor
        noteId={openNoteId}
        onDone={() => setEditing(false)}
        onSaved={() => touchCached(bookId)}
        className={className}
      />
    );
  }

  if (openNoteId) {
    return (
      <NoteView
        noteId={openNoteId}
        onBack={() => {
          setOpenNoteId(null);
          setEditing(false);
          // Editing marked the cache stale; reading left it fresh. Refresh only
          // when something actually changed, so reading a note stays free.
          if (!isFresh(useNotesCache.getState().byBook[bookId])) {
            void fetchSessions();
          }
        }}
        onEdit={() => setEditing(true)}
        onCitationClick={onCitationClick}
        className={className}
      />
    );
  }

  return (
    <div className={cn("flex flex-col h-full", className)}>
      {/* Header with new session button */}
      <div className="shrink-0 px-4 py-3 border-b border-border-subtle">
        <div className="flex items-center justify-between">
          <span className="font-heading text-body-sm font-semibold text-text-primary">
            Notes
          </span>
        </div>
        <div className="mt-2 space-y-1.5">
          <button
            onClick={() => setShowSheet(true)}
            className="flex items-center gap-1.5 w-full px-3 py-2 rounded-md bg-accent/10 text-accent text-body-sm hover:bg-accent/20 transition-colors"
          >
            <Sparkles className="h-3.5 w-3.5" strokeWidth={1.5} />
            New note
          </button>
          <button
            onClick={() => setModalMode("paste")}
            className="flex items-center gap-1.5 w-full px-3 py-2 rounded-md bg-bg-elevated text-text-muted text-body-sm hover:text-text-primary transition-colors"
          >
            <Plus className="h-3.5 w-3.5" strokeWidth={1.5} />
            Paste notes
          </button>
        </div>
      </div>

      {/* Session list — scrollable */}
      <div className="flex-1 overflow-y-auto">
        {sectionHeading && backlinks && backlinks.length > 0 && (
          <div className="border-b border-border-subtle bg-bg-elevated/40 px-4 py-3">
            <p className="text-body-sm text-text-subtle">On this section</p>
            <p className="text-body-sm text-text-primary truncate">
              {sectionHeading}
            </p>
            <div className="mt-2 space-y-1">
              {backlinks.map((note) => (
                <button
                  key={note.id}
                  onClick={() => setOpenNoteId(note.id)}
                  className="flex w-full items-center gap-1.5 rounded px-2 py-1.5 text-left text-body-sm text-text-primary hover:bg-bg-base transition-colors"
                >
                  <FileText
                    className="h-3.5 w-3.5 shrink-0 text-text-subtle"
                    strokeWidth={1.5}
                  />
                  <span className="truncate">
                    {note.title ?? "Untitled note"}
                  </span>
                </button>
              ))}
            </div>
          </div>
        )}
        {loading ? (
          <div className="flex items-center justify-center py-12">
            <Loader />
          </div>
        ) : error ? (
          <div className="flex flex-col items-center justify-center px-4 py-8 text-center">
            <p className="text-body-sm text-state-error mb-3">{error}</p>
            <button
              onClick={() => {
                setLoading(true);
                fetchSessions();
              }}
              className="px-3 py-1.5 rounded-md bg-bg-elevated text-body-sm text-text-primary hover:bg-bg-surface transition-colors"
            >
              Try again
            </button>
          </div>
        ) : sessions.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12 px-4 text-center">
            <FileText className="h-8 w-8 text-text-subtle mb-3" />
            <p className="text-body text-text-muted mb-1">No notes yet</p>
            <p className="text-body-sm text-text-subtle">
              Start a note to keep what you learn from this book.
            </p>
          </div>
        ) : (
          <div className="divide-y divide-border-subtle">
            {sessions.map((session) => (
              <button
                key={session.id}
                onClick={() => setOpenNoteId(session.id)}
                className="flex items-center gap-2 w-full px-4 py-3 text-left hover:bg-bg-elevated/50 transition-colors"
              >
                <ChevronRight className="h-3.5 w-3.5 text-text-subtle shrink-0" />
                <div className="flex-1 min-w-0">
                  <p className="text-body-sm text-text-primary truncate">
                    {session.title ?? "Untitled session"}
                  </p>
                  <div className="flex items-center gap-2 mt-0.5">
                    <span className="text-body-sm text-text-subtle">
                      {formatDate(session.created_at)}
                    </span>
                    <span className="text-body-sm text-text-subtle">·</span>
                    <span className="text-body-sm text-text-subtle">
                      {session.source === "ai_generated" ? "AI" : "Written"}
                    </span>
                    {session.matched_section_count !== null && (
                      <>
                        <span className="text-body-sm text-text-subtle">·</span>
                        <span className="text-body-sm text-text-subtle">
                          {session.matched_section_count} sections
                        </span>
                      </>
                    )}
                  </div>
                </div>
                <span
                  className={cn(
                    "text-body-sm",
                    session.status === "completed"
                      ? "text-state-success"
                      : session.status === "failed"
                        ? "text-state-error"
                        : "text-state-warning",
                  )}
                >
                  {session.status}
                </span>
              </button>
            ))}
          </div>
        )}
      </div>

      {/* AI Generate button (always visible below list) */}
      {sessions.length > 0 && (
        <div className="shrink-0 px-4 py-3 border-t border-border-subtle">
          <button
            onClick={() => setModalMode("ai_generate")}
            className="flex items-center gap-1.5 w-full px-3 py-2 rounded-md bg-bg-elevated text-text-muted text-body-sm hover:text-text-primary transition-colors"
          >
            <Sparkles className="h-3.5 w-3.5" strokeWidth={1.5} />
            Generate AI notes
          </button>
        </div>
      )}

      {showSheet && (
        <NewNoteSheet
          bookId={bookId}
          onClose={() => setShowSheet(false)}
          onCreated={(noteId, edit) => {
            setShowSheet(false);
            touchCached(bookId);
            void fetchSessions();
            setOpenNoteId(noteId);
            if (edit) setEditing(true);
          }}
        />
      )}

      {/* ── Modal ────────────────────────────────────────── */}
      {modalMode && (
        <div className="absolute inset-0 z-50 flex items-end sm:items-center justify-center bg-black/60">
          <div className="w-full sm:max-w-md bg-bg-surface rounded-t-xl sm:rounded-xl border border-border shadow-xl overflow-hidden">
            {/* Modal header */}
            <div className="flex items-center justify-between px-4 py-3 border-b border-border-subtle">
              <span className="font-heading text-body-sm font-semibold text-text-primary">
                {modalMode === "paste"
                  ? "Add note session"
                  : "Generate AI notes"}
              </span>
              <button
                onClick={() => setModalMode(null)}
                className="w-7 h-7 flex items-center justify-center rounded-md text-text-subtle hover:text-text-primary hover:bg-bg-elevated transition-colors"
              >
                <X className="h-4 w-4" strokeWidth={1.5} />
              </button>
            </div>

            {modalMode === "paste" ? (
              /* ── Paste notes form ── */
              <div className="p-4 space-y-3">
                <input
                  type="text"
                  value={pasteTitle}
                  onChange={(e) => setPasteTitle(e.target.value)}
                  placeholder="Session title (optional)"
                  className="w-full px-3 py-2 rounded-md bg-bg-base border border-border text-body-sm text-text-primary placeholder-text-subtle outline-none focus:border-accent/50 transition-colors"
                />
                <textarea
                  value={pasteText}
                  onChange={(e) => setPasteText(e.target.value)}
                  placeholder="Paste or type your lecture notes here…"
                  rows={8}
                  className="w-full px-3 py-2 rounded-md bg-bg-base border border-border text-body-sm text-text-primary placeholder-text-subtle outline-none focus:border-accent/50 transition-colors resize-none"
                />
                <div className="flex justify-end gap-2">
                  <button
                    onClick={() => setModalMode(null)}
                    className="px-3 py-1.5 rounded-md text-body-sm text-text-muted hover:text-text-primary transition-colors"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={handlePasteSubmit}
                    disabled={!pasteText.trim() || submitting}
                    className="px-3 py-1.5 rounded-md bg-accent text-white text-body-sm hover:bg-accent-hover transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
                  >
                    {submitting ? (
                      <Loader variant="dots" />
                    ) : (
                      "Submit"
                    )}
                  </button>
                </div>
              </div>
            ) : (
              /* ── AI generate form ── */
              <div className="p-4 space-y-3">
                <p className="text-body-sm text-text-muted">
                  Generate AI study notes for a chapter range.
                </p>
                <div className="flex items-center gap-3">
                  <div className="flex-1">
                    <label className="text-body-sm text-text-subtle block mb-1">
                      From chapter
                    </label>
                    <input
                      type="number"
                      min={0}
                      value={chapterStart}
                      onChange={(e) =>
                        setChapterStart(parseInt(e.target.value, 10) || 0)
                      }
                      className="w-full px-3 py-2 rounded-md bg-bg-base border border-border text-body-sm text-text-primary outline-none focus:border-accent/50 transition-colors"
                    />
                  </div>
                  <div className="flex-1">
                    <label className="text-body-sm text-text-subtle block mb-1">
                      To chapter
                    </label>
                    <input
                      type="number"
                      min={0}
                      value={chapterEnd}
                      onChange={(e) =>
                        setChapterEnd(parseInt(e.target.value, 10) || 0)
                      }
                      className="w-full px-3 py-2 rounded-md bg-bg-base border border-border text-body-sm text-text-primary outline-none focus:border-accent/50 transition-colors"
                    />
                  </div>
                </div>
                <div className="flex justify-end gap-2 pt-2">
                  <button
                    onClick={() => setModalMode(null)}
                    className="px-3 py-1.5 rounded-md text-body-sm text-text-muted hover:text-text-primary transition-colors"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={handleAiGenerate}
                    disabled={chapterEnd < chapterStart || generating}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-accent text-white text-body-sm hover:bg-accent-hover transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
                  >
                    {generating ? (
                      <>
                        <Loader variant="dots" />
                        Generating…
                      </>
                    ) : (
                      <>
                        <Sparkles className="h-3.5 w-3.5" strokeWidth={1.5} />
                        Generate
                      </>
                    )}
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}