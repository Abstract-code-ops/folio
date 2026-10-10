import { create } from "zustand";
import { persist } from "zustand/middleware";

export interface Citation {
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
}

interface ChatStore {
  chats: Record<string, ChatState>;
  getChat: (bookId: string) => ChatState;
  addMessage: (bookId: string, msg: ChatMessage) => void;
  appendToken: (bookId: string, text: string) => void;
  setCitations: (bookId: string, citations: Citation[]) => void;
  setNotCovered: (bookId: string, text: string) => void;
  setSummary: (bookId: string, summary: string) => void;
  clearMessages: (bookId: string) => void;
  dropOldest: (bookId: string, count: number) => void;
  resetChat: (bookId: string) => void;
}

const emptyChat = (): ChatState => ({ messages: [], summary: null });

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

      setSummary: (bookId, summary) =>
        set((s) => {
          const chat = s.chats[bookId] ?? emptyChat();
          return { chats: { ...s.chats, [bookId]: { ...chat, summary } } };
        }),

      clearMessages: (bookId) =>
        set((s) => {
          const chat = s.chats[bookId];
          if (!chat) return s;
          return { chats: { ...s.chats, [bookId]: { ...chat, messages: [] } } };
        }),

      dropOldest: (bookId, count) =>
        set((s) => {
          const chat = s.chats[bookId];
          if (!chat || count <= 0) return s;
          return {
            chats: { ...s.chats, [bookId]: { ...chat, messages: chat.messages.slice(count) } },
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
