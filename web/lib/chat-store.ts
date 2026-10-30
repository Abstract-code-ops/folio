import { create } from "zustand";
import { persist } from "zustand/middleware";

export interface Citation {
  /** Passage number the answer cited, e.g. `[2]`. Absent on older persisted chats. */
  passage?: number;
  sectionHeading: string;
  pageStart: number | null;
  pageEnd: number | null;
  excerpt: string;
}

export type ChatMessage =
  | { role: "user"; text: string }
  | { role: "ai"; text: string; citations: Citation[]; notCovered: string | null };

export interface ChatState {
  messages: ChatMessage[];
  summary: string | null;
  /**
   * How many leading messages are already folded into `summary`.
   *
   * The thread keeps every message on screen. This only marks where the backend
   * summary takes over, so a request can send the summary plus the uncovered
   * tail instead of the whole transcript.
   */
  summarizedCount: number;
}

/** A chat is now a session — a book can have several, opened and closed freely. */
export interface ChatSession extends ChatState {
  id: string;
  bookId: string;
  title: string | null;
  createdAt: number;
  updatedAt: number;
}

function newId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `c-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

const emptySession = (bookId: string): ChatSession => {
  const now = Date.now();
  return {
    id: newId(),
    bookId,
    title: null,
    messages: [],
    summary: null,
    summarizedCount: 0,
    createdAt: now,
    updatedAt: now,
  };
};

interface ChatStore {
  sessions: Record<string, ChatSession>;
  /** The session each book's panel is showing. */
  activeByBook: Record<string, string>;
  /** A question seeded from a PDF selection, waiting for the chat to pick it up. */
  pendingSeed: { bookId: string; text: string } | null;

  listSessions: (bookId: string) => ChatSession[];
  getSession: (id: string) => ChatSession | undefined;
  activeSessionId: (bookId: string) => string | null;
  createSession: (bookId: string) => string;
  deleteSession: (id: string) => void;
  setActive: (bookId: string, id: string) => void;

  setPendingSeed: (bookId: string, text: string) => void;
  consumeSeed: (bookId: string) => string | null;

  addMessage: (id: string, msg: ChatMessage) => void;
  appendToken: (id: string, text: string) => void;
  setCitations: (id: string, citations: Citation[]) => void;
  setNotCovered: (id: string, text: string) => void;
  applySummary: (id: string, summary: string | null, summarizedCount: number) => void;
}

const patchSession = (
  sessions: Record<string, ChatSession>,
  id: string,
  patch: (session: ChatSession) => ChatSession,
) => {
  const session = sessions[id];
  if (!session) return sessions;
  return { ...sessions, [id]: patch(session) };
};

export const useChatStore = create<ChatStore>()(
  persist(
    (set, get) => ({
      sessions: {},
      activeByBook: {},
      pendingSeed: null,

      listSessions: (bookId) =>
        Object.values(get().sessions)
          .filter((s) => s.bookId === bookId)
          .sort((a, b) => b.updatedAt - a.updatedAt),

      getSession: (id) => get().sessions[id],

      activeSessionId: (bookId) => {
        const active = get().activeByBook[bookId];
        if (active && get().sessions[active]) return active;
        const list = get().listSessions(bookId);
        return list[0]?.id ?? null;
      },

      createSession: (bookId) => {
        const session = emptySession(bookId);
        set((s) => ({
          sessions: { ...s.sessions, [session.id]: session },
          activeByBook: { ...s.activeByBook, [bookId]: session.id },
        }));
        return session.id;
      },

      deleteSession: (id) =>
        set((s) => {
          const sessions = { ...s.sessions };
          delete sessions[id];
          const activeByBook = { ...s.activeByBook };
          for (const [bookId, activeId] of Object.entries(activeByBook)) {
            if (activeId === id) delete activeByBook[bookId];
          }
          return { sessions, activeByBook };
        }),

      setActive: (bookId, id) =>
        set((s) => ({ activeByBook: { ...s.activeByBook, [bookId]: id } })),

      setPendingSeed: (bookId, text) =>
        set({ pendingSeed: { bookId, text } }),

      consumeSeed: (bookId) => {
        const seed = get().pendingSeed;
        if (!seed || seed.bookId !== bookId) return null;
        set({ pendingSeed: null });
        return seed.text;
      },

      addMessage: (id, msg) =>
        set((s) => ({
          sessions: patchSession(s.sessions, id, (session) => ({
            ...session,
            messages: [...session.messages, msg],
            updatedAt: Date.now(),
          })),
        })),

      appendToken: (id, text) =>
        set((s) => ({
          sessions: patchSession(s.sessions, id, (session) => {
            const messages = [...session.messages];
            const last = messages[messages.length - 1];
            if (last && last.role === "ai") {
              messages[messages.length - 1] = { ...last, text: last.text + text };
            }
            return { ...session, messages };
          }),
        })),

      setCitations: (id, citations) =>
        set((s) => ({
          sessions: patchSession(s.sessions, id, (session) => {
            const messages = [...session.messages];
            const last = messages[messages.length - 1];
            if (last && last.role === "ai") {
              messages[messages.length - 1] = { ...last, citations };
            }
            return { ...session, messages };
          }),
        })),

      setNotCovered: (id, text) =>
        set((s) => ({
          sessions: patchSession(s.sessions, id, (session) => {
            const messages = [...session.messages];
            const last = messages[messages.length - 1];
            if (last && last.role === "ai") {
              messages[messages.length - 1] = { ...last, notCovered: text };
            }
            return { ...session, messages };
          }),
        })),

      applySummary: (id, summary, summarizedCount) =>
        set((s) => ({
          sessions: patchSession(s.sessions, id, (session) => ({
            ...session,
            summary,
            summarizedCount,
          })),
        })),
    }),
    { name: "folio-chat-sessions" },
  ),
);
