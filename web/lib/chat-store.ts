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
   * tail instead of the whole transcript. Absent on chats persisted before this
   * field existed, hence `?? 0` at the read sites.
   */
  summarizedCount: number;
}

interface ChatStore {
  chats: Record<string, ChatState>;
  getChat: (bookId: string) => ChatState;
  addMessage: (bookId: string, msg: ChatMessage) => void;
  appendToken: (bookId: string, text: string) => void;
  setCitations: (bookId: string, citations: Citation[]) => void;
  setNotCovered: (bookId: string, text: string) => void;
  /**
   * Record a new rolling summary and how much of the thread it covers.
   *
   * Messages are never removed: the visible conversation is the student's
   * record, and compacting it is the backend's problem, not the UI's.
   */
  applySummary: (bookId: string, summary: string, summarizedCount: number) => void;
  resetChat: (bookId: string) => void;
}

const emptyChat = (): ChatState => ({
  messages: [],
  summary: null,
  summarizedCount: 0,
});

// Persisted (localStorage) so chat history survives leaving/re-entering the
// chat tab. Keyed by bookId — each book has its own thread.
export const useChatStore = create<ChatStore>()(
  persist(
    (set, get) => ({
      chats: {},

      getChat: (bookId) => get().chats[bookId] ?? emptyChat(),

      addMessage: (bookId, msg) =>
        set((s) => {
          const chat = s.chats[bookId] ?? emptyChat();
          return {
            chats: { ...s.chats, [bookId]: { ...chat, messages: [...chat.messages, msg] } },
          };
        }),

      appendToken: (bookId, text) =>
        set((s) => {
          const chat = s.chats[bookId];
          if (!chat) return s;
          const messages = [...chat.messages];
          const last = messages[messages.length - 1];
          if (last && last.role === "ai") {
            messages[messages.length - 1] = { ...last, text: last.text + text };
          }
          return { chats: { ...s.chats, [bookId]: { ...chat, messages } } };
        }),

      setCitations: (bookId, citations) =>
        set((s) => {
          const chat = s.chats[bookId];
          if (!chat) return s;
          const messages = [...chat.messages];
          const last = messages[messages.length - 1];
          if (last && last.role === "ai") {
            messages[messages.length - 1] = { ...last, citations };
          }
          return { chats: { ...s.chats, [bookId]: { ...chat, messages } } };
        }),

      setNotCovered: (bookId, text) =>
        set((s) => {
          const chat = s.chats[bookId];
          if (!chat) return s;
          const messages = [...chat.messages];
          const last = messages[messages.length - 1];
          if (last && last.role === "ai") {
            messages[messages.length - 1] = { ...last, notCovered: text };
          }
          return { chats: { ...s.chats, [bookId]: { ...chat, messages } } };
        }),

      applySummary: (bookId, summary, summarizedCount) =>
        set((s) => {
          const chat = s.chats[bookId] ?? emptyChat();
          return {
            chats: {
              ...s.chats,
              [bookId]: { ...chat, summary, summarizedCount },
            },
          };
        }),

      resetChat: (bookId) =>
        set((s) => {
          if (!s.chats[bookId]) return s;
          const chats = { ...s.chats };
          delete chats[bookId];
          return { chats };
        }),
    }),
    { name: "folio-chat" }
  )
);
