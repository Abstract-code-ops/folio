"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Send, MessageSquare, ExternalLink, Trash2, Plus, X, RotateCcw, RefreshCw } from "lucide-react";
import { cn } from "@/lib/utils";
import { apiClient } from "@/lib/api-client";
import { pullLatest } from "@/lib/sync";
import { GUEST_QA_LIMIT, isAuthed } from "@/lib/guest";
import ReactMarkdown from "react-markdown";
import remarkMath from "remark-math";
import remarkGfm from "remark-gfm";
import rehypeKatex from "rehype-katex";
import rehypeHighlight from "rehype-highlight";
import "katex/dist/katex.min.css";
import "highlight.js/styles/github-dark.css";
import { ThinkingAnimation } from "@/components/ui/thinking-animation";
import type { QaEvent } from "@/types/chat";
import {
  useChatStore,
  type ChatMessage,
  type ChatSession,
  type Citation,
} from "@/lib/chat-store";

// KaTeX (math) + highlight.js (code). Hoisted to module scope: a new array identity
// would re-run the whole markdown pipeline on every render — which, mid-stream,
// is every commit. Typed `any` to avoid pulling in "unified"'s types as a dep.
const REMARK_PLUGINS: any = [remarkMath, remarkGfm];
const REHYPE_PLUGINS: any = [
  [rehypeKatex, { throwOnError: false, strict: "ignore" }],
  [rehypeHighlight, { detect: false, plainText: ["txt", "text", "output"] }],
];

// GFM gives tables + autolinks. Wrap tables so a wide one scrolls horizontally
// instead of overflowing the message column.
const MARKDOWN_COMPONENTS: any = {
  table: ({ node: _node, ...props }: any) => (
    <div className="my-2 overflow-x-auto">
      <table className="border-collapse" {...props} />
    </div>
  ),
};

const THINKING_LABELS = ["Thinking…", "Reading the book…", "Working out an answer…"];

// Shown while the request is in flight but no answer token has arrived yet —
// covers routing + retrieval + the model's silent reasoning phase.
function ThinkingIndicator() {
  const [index, setIndex] = useState(0);
  useEffect(() => {
    const timer = setInterval(
      () => setIndex((n) => (n + 1) % THINKING_LABELS.length),
      1600,
    );
    return () => clearInterval(timer);
  }, []);
  return (
    <div className="flex items-center gap-2 rounded-lg rounded-bl-sm bg-bg-elevated px-3 py-2 text-body-sm text-text-muted">
      <ThinkingAnimation />
      <span key={index} className="animate-pulse">
        {THINKING_LABELS[index]}
      </span>
    </div>
  );
}

// Keep this many recent messages visible; summarize anything older.
const RECENT_KEEP = 6;
// Trigger summarization once the thread grows past this many messages.
const MAX_VISIBLE = RECENT_KEEP + 4;

export interface ChatPanelProps {
  bookId: string;
  /** Example questions for the empty state, normally built from book headings. */
  suggestions?: string[];
  /** Called when a citation is clicked — the parent jumps to the page and highlights the cited text */
  onCitationClick?: (target: { page: number; text: string }) => void;
  className?: string;
}

/** A tab label: the title if set, else the first user message, else "New chat". */
function sessionLabel(session: ChatSession): string {
  if (session.title) return session.title;
  const first = session.messages.find((m) => m.role === "user" && m.text.trim());
  if (first) return first.text.trim().slice(0, 24);
  return "New chat";
}

export function ChatPanel({ bookId, suggestions = [], onCitationClick, className }: ChatPanelProps) {
  const sessions = useChatStore((s) => s.sessions);
  const activeByBook = useChatStore((s) => s.activeByBook);
  const list = useMemo(
    () =>
      Object.values(sessions)
        .filter((s) => s.bookId === bookId)
        .sort((a, b) => b.updatedAt - a.updatedAt),
    [sessions, bookId],
  );

  const activeId =
    activeByBook[bookId] && sessions[activeByBook[bookId]]
      ? activeByBook[bookId]
      : list[0]?.id ?? null;
  const active = activeId ? sessions[activeId] : undefined;
  const messages = active?.messages ?? [];

  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [thinking, setThinking] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [cooldown, setCooldown] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [confirmClear, setConfirmClear] = useState(false);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  // Auto-scroll on new messages
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // A PDF selection seeds a question; it is auto-sent once the session exists
  // (see the effect after sendQuestion).

  const createSession = useCallback(() => {
    useChatStore.getState().createSession(bookId);
    setInput("");
    setError(null);
  }, [bookId]);

  const deleteSession = useCallback(
    (id: string) => {
      const store = useChatStore.getState();
      store.deleteSession(id);
      setError(null);
    },
    [],
  );

  const setActive = useCallback(
    (id: string) => {
      useChatStore.getState().setActive(bookId, id);
      setInput("");
      setError(null);
    },
    [bookId],
  );

  // Fold older messages into the rolling summary. The thread itself is never
  // trimmed: the student keeps their whole conversation on screen, and only the
  // request payload is compacted.
  const rollUpIfNeeded = useCallback(
    async (sessionId: string) => {
      const store = useChatStore.getState();
      const chat = store.getSession(sessionId);
      if (!chat) return;
      const covered = chat.summarizedCount ?? 0;
      const uncovered = chat.messages.length - covered;
      if (uncovered <= MAX_VISIBLE) return;

      const overflow = uncovered - RECENT_KEEP;
      const toSummarize = chat.messages.slice(covered, covered + overflow);

      const transcript: { role: string; content: string }[] = [];
      if (chat.summary) {
        transcript.push({ role: "user", content: `[Earlier conversation]\n${chat.summary}` });
      }
      for (const m of toSummarize) {
        if (m.text.trim()) transcript.push({ role: m.role, content: m.text });
      }

      try {
        const newSummary = await apiClient.summarizeConversation(transcript);
        if (newSummary) {
          store.applySummary(sessionId, newSummary, covered + overflow);
        }
      } catch {
        // Summarization is best-effort — keep the messages if it fails.
      }
    },
    [],
  );

  const sendQuestion = useCallback(
    async (textOverride?: string) => {
      const q = (textOverride ?? input).trim();
      if (!q || streaming) return;
      if (textOverride === undefined) {
        setInput("");
        if (inputRef.current) inputRef.current.style.height = "auto";
      }
      setError(null);

    const store = useChatStore.getState();
    // A chat session exists by the time you send: create one if the panel has
    // none open.
    const sessionId = activeId ?? store.createSession(bookId);
    const chat = store.getSession(sessionId);
    if (!chat) return;

    // Guest trial: unauthenticated visitors get GUEST_QA_LIMIT questions, none
    // persisted server-side. At the cap, prompt sign-in.
    if (!isAuthed()) {
      const asked = store
        .listSessions(bookId)
        .reduce((n, s) => n + s.messages.filter((m) => m.role === "user").length, 0);
      if (asked >= GUEST_QA_LIMIT) {
        setError(`You've used your ${GUEST_QA_LIMIT} free questions — sign in to keep going.`);
        return;
      }
    }

    // Only the messages the summary does not already cover go to the backend.
    const covered = chat.summarizedCount ?? 0;
    const history: { role: string; content: string }[] = [];
    for (const m of chat.messages.slice(covered)) {
      if (m.text.trim()) history.push({ role: m.role, content: m.text });
    }

    store.addMessage(sessionId, { role: "user", text: q });
    store.addMessage(sessionId, {
      role: "ai",
      text: "",
      citations: [],
      notCovered: null,
    });
    setStreaming(true);
    setThinking(true);
    let gotToken = false;

    // Reveal tokens at a deliberate pace instead of as fast as the network
    // delivers them. The buffer holds raw deltas; the writer drains it smoothly.
    const buffer = { text: "" };
    let streamFinished = false;
    const reduceMotion =
      typeof window !== "undefined" &&
      window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));
    const writer = (async () => {
      while (!streamFinished || buffer.text.length > 0) {
        if (buffer.text.length === 0) {
          await sleep(14);
          continue;
        }
        if (reduceMotion) {
          const all = buffer.text;
          buffer.text = "";
          useChatStore.getState().appendToken(sessionId, all);
          continue;
        }
        // Catch up when the network bursts: reveal more per tick for a backlog,
        // one char at a time for a trickle.
        const take = Math.max(2, Math.ceil(buffer.text.length / 12));
        const chunk = buffer.text.slice(0, take);
        buffer.text = buffer.text.slice(take);
        useChatStore.getState().appendToken(sessionId, chunk);
        await sleep(12);
      }
    })();

    // Watchdog: abort if the provider sends nothing for 60s, so a hung provider
    // does not leave the user waiting; the error offers a retry.
    const controller = new AbortController();
    let watchdog: ReturnType<typeof setTimeout> | null = null;
    const bump = () => {
      if (watchdog) clearTimeout(watchdog);
      watchdog = setTimeout(() => controller.abort(), 90000);
    };
    bump();

    let currentCitations: Citation[] = [];

    try {
      const stream = await apiClient.askQuestion(bookId, q, {
        summary: chat.summary ?? undefined,
        history,
        signal: controller.signal,
      });
      const reader = stream.getReader();

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const event = value as QaEvent;
        bump();

        switch (event.type) {
          case "token":
            buffer.text += event.text;
            if (!gotToken) {
              gotToken = true;
              setThinking(false);
            }
            break;

          case "citation":
            currentCitations.push({
              passage: event.passage,
              sectionHeading: event.section_heading,
              pageStart: event.page_start,
              pageEnd: event.page_end,
              excerpt: event.excerpt,
            });
            useChatStore.getState().setCitations(sessionId, [...currentCitations]);
            break;

          case "not_covered":
            useChatStore.getState().setNotCovered(sessionId, event.text);
            break;

          case "error":
            setError(event.text);
            break;

          case "done":
            break;
        }
      }
    } catch (err) {
      if (controller.signal.aborted) {
        setError(
          "The assistant took too long (90s without a response). Retry the question.",
        );
      } else {
        setError(err instanceof Error ? err.message : "Failed to get answer");
      }
    } finally {
      if (watchdog) clearTimeout(watchdog);
      streamFinished = true;
      // Recover the UI first, so a stalled writer can never leave the panel
      // stuck on "thinking"; then best-effort drain the typewriter.
      setThinking(false);
      setStreaming(false);
      await Promise.race([writer, sleep(3000)]);
      inputRef.current?.focus();
      await rollUpIfNeeded(sessionId);
    }
  }, [input, streaming, bookId, activeId, rollUpIfNeeded]);

  // Resend a user message: drop it and everything after it, then ask it again.
  const resendFrom = useCallback(
    (index: number) => {
      if (!activeId || streaming) return;
      const store = useChatStore.getState();
      const chat = store.getSession(activeId);
      const target = chat?.messages[index];
      if (!chat || !target || target.role !== "user") return;
      store.truncateTo(activeId, index);
      void sendQuestion(target.text);
    },
    [activeId, streaming, sendQuestion],
  );

  // Auto-send a question seeded from a PDF selection ("Ask chat"). Placed after
  // sendQuestion so it can call it.
  useEffect(() => {
    if (!activeId) return;
    const seed = useChatStore.getState().consumeSeed(bookId);
    if (seed) void sendQuestion(seed);
  }, [activeId, bookId, sendQuestion]);

  // Clearing is destructive, so it takes two taps.
  useEffect(() => {
    if (!confirmClear) return;
    const timer = setTimeout(() => setConfirmClear(false), 3000);
    return () => clearTimeout(timer);
  }, [confirmClear]);

  // Get latest from the server (read-only pull), rate-limited with a short cooldown.
  useEffect(() => {
    if (cooldown <= 0) return;
    const timer = setTimeout(() => setCooldown((c) => c - 1), 1000);
    return () => clearTimeout(timer);
  }, [cooldown]);

  const doSync = useCallback(async () => {
    if (syncing || cooldown > 0) return;
    setSyncing(true);
    try {
      await pullLatest(bookId);
    } catch {
      // best-effort; the button re-enables after the cooldown
    } finally {
      setSyncing(false);
      setCooldown(15);
    }
  }, [bookId, syncing, cooldown]);

  const handleClearChat = useCallback(() => {
    if (!activeId) return;
    if (!confirmClear) {
      setConfirmClear(true);
      return;
    }
    // Clearing a session keeps the session but empties its thread.
    const store = useChatStore.getState();
    store.applySummary(activeId, null, 0);
    // There is no "clear messages" op, so delete + recreate in place.
    const bookIdHere = store.getSession(activeId)?.bookId ?? bookId;
    store.deleteSession(activeId);
    store.createSession(bookIdHere);
    setConfirmClear(false);
    setError(null);
  }, [confirmClear, activeId, bookId]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        sendQuestion();
      }
    },
    [sendQuestion],
  );

  const handleInputChange = (event: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(event.target.value);
    const el = event.target;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  };

  const handleCitationClick = useCallback(
    (citation: Citation) => {
      if (!citation.pageStart) return;
      onCitationClick?.({ page: citation.pageStart, text: citation.excerpt });
    },
    [onCitationClick],
  );

  return (
    <div className={cn("flex min-h-0 flex-1 flex-col", className)}>
      {/* Session tabs + new chat */}
      <div className="shrink-0 flex items-center gap-1 border-b border-border-subtle px-2 py-1.5 overflow-x-auto overscroll-contain">
        {list.map((session) => {
          const isActive = session.id === activeId;
          return (
            <div
              key={session.id}
              className={cn(
                "group flex shrink-0 items-center gap-1 rounded-md border px-2 py-1 text-body-sm transition-colors",
                isActive
                  ? "border-accent/40 bg-accent/10 text-text-primary"
                  : "border-transparent text-text-muted hover:bg-bg-elevated",
              )}
            >
              <button
                onClick={() => setActive(session.id)}
                className="max-w-[120px] truncate text-body-sm"
              >
                {sessionLabel(session)}
              </button>
              <button
                onClick={() => deleteSession(session.id)}
                aria-label={`Delete ${sessionLabel(session)}`}
                className="text-text-subtle hover:text-state-error"
              >
                <X className="h-3.5 w-3.5" strokeWidth={1.5} />
              </button>
            </div>
          );
        })}
        <button
          onClick={createSession}
          aria-label="New chat"
          className="flex min-h-11 min-w-11 shrink-0 items-center justify-center rounded-md text-text-muted transition-colors hover:bg-bg-elevated hover:text-text-primary sm:min-h-0 sm:min-w-8"
        >
          <Plus className="h-4 w-4" strokeWidth={1.5} />
        </button>
        <button
          onClick={doSync}
          disabled={syncing || cooldown > 0}
          aria-label="Get latest chat and notes from the server"
          title="Pull the latest chat + notes from the server (across devices)"
          className="ml-auto flex min-h-11 shrink-0 items-center gap-1 rounded-md px-2 py-1 text-body-sm text-text-muted transition-colors hover:bg-bg-elevated hover:text-text-primary disabled:opacity-50 sm:min-h-0"
        >
          <RefreshCw
            className={cn("h-3.5 w-3.5", syncing && "animate-spin")}
            strokeWidth={1.5}
          />
          {syncing ? "Syncing…" : cooldown > 0 ? `${cooldown}s` : "Get latest"}
        </button>
      </div>

      {/* Empty state */}
      {messages.length === 0 && !error && (
        <div className="flex-1 flex flex-col items-center justify-center px-6 text-center">
          <MessageSquare className="h-8 w-8 text-text-subtle mb-3" />
          <p className="mb-1 text-body text-text-muted">
            Ask a question about this book
          </p>
          <p className="mb-4 max-w-[240px] text-body-sm text-text-subtle">
            Answers come only from this book, and each one cites the pages it
            used.
          </p>
          {suggestions.length > 0 && (
            <div className="flex w-full flex-col gap-1.5">
              <span className="text-left text-body-sm text-text-subtle">Try</span>
              {suggestions.slice(0, 3).map((suggestion) => (
                <button
                  key={suggestion}
                  onClick={() => {
                    setInput(suggestion);
                    inputRef.current?.focus();
                  }}
                  className="min-h-11 rounded-md border border-border-subtle px-3 py-2 text-left text-body-sm text-text-primary transition-colors hover:bg-bg-elevated sm:min-h-0"
                >
                  {suggestion}
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Thread header with the clear action */}
      {messages.length > 0 && (
        <div className="flex items-center justify-between border-b border-border-subtle px-3 py-1.5">
          <span className="text-body-sm text-text-subtle">{sessionLabel(active!) }</span>
          <button
            type="button"
            onClick={handleClearChat}
            disabled={streaming}
            aria-label="Clear chat"
            className={cn(
              "flex items-center gap-1.5 rounded-md px-2 py-1 text-body-sm transition-colors",
              "hover:bg-bg-elevated disabled:opacity-50 disabled:pointer-events-none",
              confirmClear ? "text-accent" : "text-text-subtle",
            )}
          >
            <Trash2 className="h-3.5 w-3.5" />
            {confirmClear ? "Confirm clear" : "Clear"}
          </button>
        </div>
      )}

      {/* Message thread */}
      {messages.length > 0 && (
        <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-3 py-4 space-y-4">
          {messages.map((msg, i) => (
            <div
              key={i}
              className={cn(
                "flex items-start gap-1",
                msg.role === "user" ? "justify-end" : "justify-start",
              )}
            >
              {msg.role === "user" && (
                <button
                  type="button"
                  onClick={() => resendFrom(i)}
                  disabled={streaming}
                  aria-label="Resend this message"
                  title="Resend — drops replies after this message and asks again"
                  className="mt-1.5 shrink-0 rounded p-1 text-text-subtle transition-colors hover:text-text-primary disabled:opacity-30"
                >
                  <RotateCcw className="h-3.5 w-3.5" strokeWidth={1.5} />
                </button>
              )}
              <div
                className={cn(
                  "text-body leading-relaxed text-text-primary",
                  msg.role === "user"
                    ? "max-w-[85%] rounded-lg rounded-br-sm bg-accent/15 px-3 py-2 font-medium"
                    : "w-full max-w-[68ch]",
                )}
              >
                {"notCovered" in msg && msg.notCovered && (
                  <p className="text-text-muted italic mb-1">{msg.notCovered}</p>
                )}

                {"text" in msg && msg.text && (
                  msg.role === "user" ? (
                    <p className="whitespace-pre-wrap">{msg.text}</p>
                  ) : (
                    <div className="space-y-2 text-text-primary [&_a]:text-accent [&_a]:underline [&_code]:rounded [&_code]:bg-bg-base [&_code]:px-1 [&_code]:text-[0.85em] [&_h1]:text-h4 [&_h1]:font-semibold [&_h2]:text-h5 [&_h2]:font-semibold [&_h3]:font-semibold [&_li]:ml-4 [&_li]:list-disc [&_ol]:ml-5 [&_ol]:list-decimal [&_p]:leading-relaxed [&_pre]:my-2 [&_pre]:overflow-x-auto [&_pre]:rounded-md [&_pre]:border [&_pre]:border-border [&_pre]:bg-bg-base [&_pre]:p-3 [&_pre_code]:bg-transparent [&_pre_code]:p-0 [&_strong]:font-semibold [&_ul]:ml-4 [&_ul]:list-disc [&_table]:border-collapse [&_th]:border [&_th]:border-border [&_th]:px-2 [&_th]:py-1 [&_th]:text-left [&_th]:font-semibold [&_td]:border [&_td]:border-border [&_td]:px-2 [&_td]:py-1">
                      <ReactMarkdown
                        remarkPlugins={REMARK_PLUGINS}
                        rehypePlugins={REHYPE_PLUGINS}
                        components={MARKDOWN_COMPONENTS}
                      >
                        {msg.text}
                      </ReactMarkdown>
                    </div>
                  )
                )}

                {"citations" in msg && msg.citations.length > 0 && (
                  <div className="mt-2 space-y-1.5 border-t border-border-subtle pt-2">
                    {msg.citations.map((cite, ci) => (
                      <button
                        key={ci}
                        onClick={() => handleCitationClick(cite)}
                        className="flex items-start gap-2 w-full text-left rounded-md bg-bg-base p-2 hover:bg-bg-elevated transition-colors group"
                      >
                        <ExternalLink className="h-3 w-3 text-accent mt-0.5 shrink-0" />
                        <div className="min-w-0">
                          <p className="text-body-sm text-text-primary truncate">
                            {typeof cite.passage === "number"
                              ? `[${cite.passage}] `
                              : ""}
                            {cite.sectionHeading}
                          </p>
                          <p className="text-body-sm text-text-subtle">
                            p. {cite.pageStart}
                            {cite.pageEnd && cite.pageEnd !== cite.pageStart
                              ? `–${cite.pageEnd}`
                              : ""}
                          </p>
                          <p className="text-body-sm text-text-muted mt-0.5 line-clamp-2">
                            {cite.excerpt}
                          </p>
                        </div>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </div>
          ))}

          {streaming && thinking && (
            <div className="flex justify-start">
              <ThinkingIndicator />
            </div>
          )}

          <div ref={bottomRef} />
        </div>
      )}

      {/* Error banner */}
      {error && (
        <div className="flex items-center justify-between gap-2 border-t border-state-error/20 bg-state-error/10 px-3 py-2">
          <p className="text-body-sm text-state-error">{error}</p>
          {messages.some((m) => m.role === "user") && (
            <button
              type="button"
              onClick={() => resendFrom(messages.map((m) => m.role).lastIndexOf("user"))}
              disabled={streaming}
              className="shrink-0 rounded-md bg-state-error/15 px-2 py-1 text-body-sm text-state-error transition-colors hover:bg-state-error/25 disabled:opacity-40"
            >
              Retry
            </button>
          )}
        </div>
      )}

      {/* Input bar */}
      <div className="shrink-0 border-t border-border-subtle p-3">
        <div className="flex items-end gap-2 bg-bg-base rounded-lg border border-border p-2 focus-within:border-accent/50 transition-colors">
          <textarea
            ref={inputRef}
            value={input}
            onChange={handleInputChange}
            onKeyDown={handleKeyDown}
            placeholder="Ask a question about this book…"
            aria-label="Ask a question about this book"
            rows={1}
            disabled={streaming}
            className="flex-1 bg-transparent text-body-sm text-text-primary placeholder-text-subtle resize-none outline-none min-h-[44px] sm:min-h-[24px] max-h-[200px] overflow-y-auto disabled:opacity-50"
          />
          <button
            onClick={() => sendQuestion()}
            aria-label="Send question"
            disabled={!input.trim() || streaming}
            className="flex items-center justify-center w-11 h-11 sm:w-8 sm:h-8 rounded-md bg-accent text-white hover:bg-accent-hover transition-colors disabled:opacity-30 disabled:cursor-not-allowed shrink-0"
          >
            <Send className="h-3.5 w-3.5" strokeWidth={1.5} />
          </button>
        </div>
      </div>
    </div>
  );
}
