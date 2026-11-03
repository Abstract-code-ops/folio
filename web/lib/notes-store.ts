import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";
import { userScopedStorage } from "./user-scope";
import { GUEST_NOTES_LIMIT, isAuthed } from "./guest";
import type {
  BlockKind,
  BlockOrigin,
  LinkOrigin,
  LinkStatus,
} from "@/types/notes";

// ── Local notes model ─────────────────────────────────────────
// Notes live in the browser (localStorage), not Postgres — the curator decision
// in docs/ui-next-steps.md and docs/progress-tracker.md ("notes move to
// local-only"). A note is the same shape as the server's, minus anything that
// only the database knew (position is implied by array order; ids are
// client-generated so links stay attached while editing).

export type LocalLink = {
  id: string;
  section_id: string | null;
  anchor_heading_path: string;
  page_start: number;
  page_end: number;
  excerpt: string;
  /** The note-side text this citation anchors to (the phrase the student selected). */
  quote?: string | null;
  status: LinkStatus;
  origin: LinkOrigin;
};

export type LocalBlock = {
  id: string;
  kind: BlockKind;
  text: string;
  origin: BlockOrigin;
  links: LocalLink[];
};

export type LocalNote = {
  id: string;
  bookId: string;
  title: string | null;
  source: LocalNoteSource;
  /** Epoch millis. */
  createdAt: number;
  updatedAt: number;
  blocks: LocalBlock[];
  /** Client-only lifecycle. Absent = settled; "generating" = AI still working. */
  status?: "generating" | "error";
  /** Human-readable error when status === "error". */
  error?: string | null;
};

/** Where a local note came from. "typed" is the editor's own output. */
export type LocalNoteSource = "typed" | "ai_generated" | "pasted";

function newId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `n-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

/** True when the note has at least one block with real text (drafts write nothing). */
export function hasContent(note: LocalNote): boolean {
  return note.blocks.some((block) => block.text.trim().length > 0);
}

/** Distinct accepted-cited section ids, for the "On this section" backlinks. */
export function citedSectionIds(note: LocalNote): string[] {
  const ids = new Set<string>();
  for (const block of note.blocks) {
    for (const link of block.links) {
      if (link.status === "dismissed") continue;
      if (link.section_id) ids.add(link.section_id);
    }
  }
  return [...ids];
}

export function makeLocalNote(
  bookId: string,
  partial?: Partial<LocalNote>,
): LocalNote {
  const now = Date.now();
  return {
    id: newId(),
    bookId,
    title: null,
    source: "typed",
    createdAt: now,
    updatedAt: now,
    blocks: [],
    ...partial,
  };
}

interface NotesStore {
  notes: Record<string, LocalNote>;
  /** Note ids deleted locally, awaiting a server delete on the next flush. */
  pendingDeletes: string[];
  listNotes: (bookId: string) => LocalNote[];
  getNote: (id: string) => LocalNote | undefined;
  saveNote: (note: LocalNote) => void;
  deleteNote: (id: string) => void;
  renameNote: (id: string, title: string | null) => void;
  addLink: (noteId: string, blockId: string, link: LocalLink) => void;
  appendBlock: (noteId: string, block: LocalBlock) => void;
  removeLink: (noteId: string, blockId: string, linkId: string) => void;
  exportNotes: () => string;
  importNotes: (json: string) => void;
  clearDeletes: (ids: string[]) => void;
}

/** All notes, keyed by id, persisted to localStorage. */
export const useNotesStore = create<NotesStore>()(
  persist(
    (set, get) => ({
      notes: {},
      pendingDeletes: [],

      listNotes: (bookId) =>
        Object.values(get().notes)
          .filter((note) => note.bookId === bookId)
          .sort((a, b) => b.updatedAt - a.updatedAt),

      getNote: (id) => get().notes[id],

      saveNote: (note) => {
        // Guest trial: cap NEW notes at GUEST_NOTES_LIMIT (updates always pass).
        const existing = get().notes[note.id];
        if (!existing && !isAuthed()) {
          const count = Object.values(get().notes).filter(
            (n) => n.bookId === note.bookId,
          ).length;
          if (count >= GUEST_NOTES_LIMIT) return;
        }
        set((state) => ({
          notes: { ...state.notes, [note.id]: { ...note, updatedAt: Date.now() } },
        }));
      },

      deleteNote: (id) =>
        set((state) => {
          const notes = { ...state.notes };
          delete notes[id];
          const pendingDeletes = state.pendingDeletes.includes(id)
            ? state.pendingDeletes
            : [...state.pendingDeletes, id];
          return { notes, pendingDeletes };
        }),

      renameNote: (id, title) =>
        set((state) => {
          const note = state.notes[id];
          if (!note) return state;
          return {
            notes: { ...state.notes, [id]: { ...note, title, updatedAt: Date.now() } },
          };
        }),

      addLink: (noteId, blockId, link) =>
        set((state) => {
          const note = state.notes[noteId];
          if (!note) return state;
          const blocks = note.blocks.map((block) =>
            block.id === blockId
              ? { ...block, links: [...block.links, link] }
              : block,
          );
          return {
            notes: { ...state.notes, [noteId]: { ...note, blocks, updatedAt: Date.now() } },
          };
        }),

      appendBlock: (noteId, block) =>
        set((state) => {
          const note = state.notes[noteId];
          if (!note) return state;
          return {
            notes: {
              ...state.notes,
              [noteId]: { ...note, blocks: [...note.blocks, block], updatedAt: Date.now() },
            },
          };
        }),

      removeLink: (noteId, blockId, linkId) =>
        set((state) => {
          const note = state.notes[noteId];
          if (!note) return state;
          const blocks = note.blocks.map((block) =>
            block.id === blockId
              ? { ...block, links: block.links.filter((link) => link.id !== linkId) }
              : block,
          );
          return {
            notes: { ...state.notes, [noteId]: { ...note, blocks, updatedAt: Date.now() } },
          };
        }),

      exportNotes: () => JSON.stringify(Object.values(get().notes)),

      importNotes: (json) => {
        try {
          const parsed = JSON.parse(json) as LocalNote[];
          const notes: Record<string, LocalNote> = {};
          for (const note of parsed) notes[note.id] = note;
          set({ notes });
        } catch {
          // A malformed import must not wipe the store — leave it untouched.
        }
      },

      clearDeletes: (ids) =>
        set((state) => ({
          pendingDeletes: state.pendingDeletes.filter((id) => !ids.includes(id)),
        })),
    }),
    {
      name: "folio-notes",
      storage: createJSONStorage(() => userScopedStorage()),
      // A background generation cannot survive a reload; a note still marked
      // "generating" at load is orphaned — flag it instead of spinning forever.
      onRehydrateStorage: () => (state) => {
        if (!state) return;
        for (const note of Object.values(state.notes)) {
          if (note.status === "generating") {
            note.status = "error";
            note.error = "Generation was interrupted. Try again.";
          }
        }
      },
    },
  ),
);

/**
 * Which note each book's panel is showing, in memory only.
 *
 * This is deliberately separate from the list cache and deliberately not
 * persisted. It lives here so the panel can unmount -- collapsing the desktop
 * sidebar, or closing a mobile sheet -- without losing whether the student was
 * reading or editing a note; a page reload starts back on the list.
 */
interface NotesNavEntry {
  openNoteId: string | null;
  editing: boolean;
}

interface NotesNavState {
  byBook: Record<string, NotesNavEntry>;
  /** Show a note (or `null` for the list). Opening always leaves edit mode. */
  open: (bookId: string, noteId: string | null) => void;
  setEditing: (bookId: string, editing: boolean) => void;
}

export const useNotesNav = create<NotesNavState>()((set) => ({
  byBook: {},
  open: (bookId, noteId) =>
    set((state) => ({
      byBook: {
        ...state.byBook,
        [bookId]: { openNoteId: noteId, editing: false },
      },
    })),
  setEditing: (bookId, editing) =>
    set((state) => ({
      byBook: {
        ...state.byBook,
        [bookId]: {
          openNoteId: state.byBook[bookId]?.openNoteId ?? null,
          editing,
        },
      },
    })),
}));
