import { apiClient } from "./api-client";
import { hasContent, useNotesStore, type LocalNote } from "./notes-store";
import type { NoteBatchNote } from "@/types/notes";

/**
 * Local-first write-behind sync.
 *
 * The browser store is the source of interaction; edits accumulate locally and
 * are flushed to Postgres when the student **finishes editing** — i.e. on the
 * editor's Done button — not on every pause. That is one write per editing
 * session instead of one per debounce tick: far fewer DB calls. Deletes ride
 * the next flush.
 *
 * Flush triggers: the editor's Done button (primary), tab hidden / pagehide
 * (safety when the tab closes mid-edit), and a long safety backstop for an edit
 * that never triggers an explicit exit.
 */

const DELETE_DEBOUNCE_MS = 1500; // deletes are discrete; flush promptly
const SAFETY_MS = 60000; // backstop for an edit with no explicit exit

/** Map a local note to the server's batch payload (typed → pasted). */
export function toBatchNote(note: LocalNote): NoteBatchNote {
  return {
    id: note.id,
    book_id: note.bookId,
    title: note.title,
    source: note.source === "ai_generated" ? "ai_generated" : "pasted",
    blocks: note.blocks.map((block) => ({
      id: block.id,
      kind: block.kind,
      text: block.text,
      origin: block.origin,
      links: block.links.map((link) => ({
        id: link.id,
        section_id: link.section_id,
        anchor_heading_path: link.anchor_heading_path,
        page_start: link.page_start,
        page_end: link.page_end,
        excerpt: link.excerpt,
        status: link.status,
        origin: link.origin,
      })),
    })),
  };
}

export type SaveNotes = (
  notes: NoteBatchNote[],
  deleted: string[],
) => Promise<void>;

export interface NoteSyncOptions {
  /** Override the transport (tests inject a mock). */
  save?: SaveNotes;
  /** Debounce used for deletes (and retries). Default 1.5s. */
  deleteDebounceMs?: number;
  /** Safety backstop for unsaved edits. Default 60s. */
  safetyMs?: number;
}

export interface NoteSync {
  markDirty: (id: string) => void;
  /** Drop a note from the outbox without saving (e.g. it was just imported). */
  markSynced: (id: string) => void;
  /** Arm the short debounce (deletes / retry). */
  scheduleFlush: () => void;
  flush: () => Promise<void>;
  stop: () => void;
}

export function createNoteSync(options: NoteSyncOptions = {}): NoteSync {
  const save: SaveNotes =
    options.save ??
    (async (notes, deleted) => {
      await apiClient.upsertNotesBatch(notes, deleted);
    });
  const deleteDebounceMs = options.deleteDebounceMs ?? DELETE_DEBOUNCE_MS;
  const safetyMs = options.safetyMs ?? SAFETY_MS;

  const dirty = new Set<string>();
  let debounceTimer: ReturnType<typeof setTimeout> | null = null;
  let safetyTimer: ReturnType<typeof setTimeout> | null = null;
  let flushing = false;

  function clearTimers() {
    if (debounceTimer) {
      clearTimeout(debounceTimer);
      debounceTimer = null;
    }
    if (safetyTimer) {
      clearTimeout(safetyTimer);
      safetyTimer = null;
    }
  }

  async function flush(): Promise<void> {
    clearTimers();
    const state = useNotesStore.getState();
    const deleted = [...state.pendingDeletes];
    if (flushing || (dirty.size === 0 && deleted.length === 0)) return;
    flushing = true;

    const ids = [...dirty];
    // Drafts and emptied notes are never written — an empty note must not
    // create a server row (the "empty note saved itself" problem).
    const payload = ids
      .map((id) => state.getNote(id))
      .filter((note): note is LocalNote => !!note && hasContent(note))
      .map(toBatchNote);

    try {
      if (payload.length > 0 || deleted.length > 0) await save(payload, deleted);
      for (const id of ids) dirty.delete(id);
      if (deleted.length > 0) useNotesStore.getState().clearDeletes(deleted);
    } catch {
      // Keep the notes dirty; retry shortly rather than losing the edit.
      debounceTimer = setTimeout(() => void flush(), deleteDebounceMs);
    } finally {
      flushing = false;
    }
  }

  // Short debounce — for deletes and for a failed-save retry.
  function scheduleFlush() {
    if (debounceTimer) clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => void flush(), deleteDebounceMs);
  }

  // Long backstop — armed by an edit, but does NOT fire per keystroke.
  function armSafety() {
    if (!safetyTimer) safetyTimer = setTimeout(() => void flush(), safetyMs);
  }

  function markDirty(id: string) {
    dirty.add(id);
    armSafety();
  }

  function markSynced(id: string) {
    dirty.delete(id);
  }

  return { markDirty, markSynced, scheduleFlush, flush, stop: clearTimers };
}

// ── App-wide instance ─────────────────────────────────────────

let instance: NoteSync | null = null;
let unsubscribeNotes: (() => void) | null = null;

/**
 * Start the write-behind engine once. Notes whose object identity changed become
 * dirty; a queued delete arms a short flush. The editor's Done button calls
 * `flushNoteSyncNow()`, so the primary write is an explicit action.
 */
export function startNoteSync(options: NoteSyncOptions = {}): NoteSync {
  if (instance) return instance;
  const sync = createNoteSync(options);
  instance = sync;

  unsubscribeNotes = useNotesStore.subscribe((state, prev) => {
    if (state.notes !== prev.notes) {
      for (const [id, note] of Object.entries(state.notes)) {
        if (prev.notes[id] !== note && hasContent(note)) sync.markDirty(id);
      }
    }
    if (
      state.pendingDeletes !== prev.pendingDeletes &&
      state.pendingDeletes.length > 0
    ) {
      sync.scheduleFlush();
    }
  });

  if (typeof window !== "undefined") {
    window.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "hidden") void sync.flush();
    });
    window.addEventListener("pagehide", () => void sync.flush());
  }

  return sync;
}

/** Flush now — called by the editor's Done button (the primary write point). */
export function flushNoteSyncNow(): Promise<void> {
  return instance ? instance.flush() : Promise.resolve();
}

/** Tell the engine a note is already on the server (used after import). */
export function markNoteSynced(id: string) {
  instance?.markSynced(id);
}

/** Test-only: tear down the app-wide instance. */
export function __resetNoteSyncForTests() {
  instance?.stop();
  instance = null;
  unsubscribeNotes?.();
  unsubscribeNotes = null;
}
