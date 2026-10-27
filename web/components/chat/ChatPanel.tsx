"use client";

import { useState, useRef, useCallback, useEffect } from "react";
import {
  Send,
  MessageSquare,
  ExternalLink,
  Trash2,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { apiClient } from "@/lib/api-client";
import { Loader } from "@/components/ui/loader";
import type { QaEvent } from "@/types/chat";
import { useChatStore, type ChatMessage, type Citation } from "@/lib/chat-store";

// Keep this many recent messages visible; summarize anything older.
const RECENT_KEEP = 6;
// Trigger summarization once the thread grows past this many messages.
const MAX_VISIBLE = RECENT_KEEP + 4;

// Stable empty reference so the messages selector doesn't churn on every render
const EMPTY_MESSAGES: ChatMessage[] = [];

// ── Component ────────────────────────────────────────────────

export interface ChatPanelProps {
  bookId: string;
  /** Called when a citation is clicked — the parent jumps to the page and highlights the cited text */
  onCitationClick?: (target: { page: number; text: string }) => void;
  className?: string;
}

export function ChatPanel({ bookId, onCitationClick, className }: ChatPanelProps) {
  const messages = useChatStore((s) => s.chats[bookId]?.messages ?? EMPTY_MESSAGES);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmClear, setConfirmClear] = useState(false);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  // Auto-scroll on new messages
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Fold older messages into the rolling summary. The thread itself is never
  // trimmed: the student keeps their whole conversation on screen, and only the
  // request payload is compacted.
  const rollUpIfNeeded = useCallback(async () => {
    const store = useChatStore.getState();
    const chat = store.getChat(bookId);
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
        store.applySummary(bookId, newSummary, covered + overflow);
      }
    } catch {
      // Summarization is best-effort — keep the messages if it fails.
    }
  }, [bookId]);

  const sendQuestion = useCallback(async () => {
    const q = input.trim();
    if (!q || streaming) return;
    setInput("");
    setError(null);

    const store = useChatStore.getState();
    const chat = store.getChat(bookId);

    // Only the messages the summary does not already cover go to the backend.
    // The full thread stays on screen regardless.
    const covered = chat.summarizedCount ?? 0;
    const history: { role: string; content: string }[] = [];
    for (const m of chat.messages.slice(covered)) {
      if (m.text.trim()) history.push({ role: m.role, content: m.text });
    }

    store.addMessage(bookId, { role: "user", text: q });
    store.addMessage(bookId, {
      role: "ai",
      text: "",
      citations: [],
      notCovered: null,
    });
    setStreaming(true);

    let currentCitations: Citation[] = [];

    try {
      const stream = await apiClient.askQuestion(bookId, q, {
        summary: chat.summary ?? undefined,
        history,
      });
      const reader = stream.getReader();

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const event = value as QaEvent;

        switch (event.type) {
          case "token":
            useChatStore.getState().appendToken(bookId, event.text);
            break;

          case "citation":
            currentCitations.push({
              passage: event.passage,
              sectionHeading: event.section_heading,
              pageStart: event.page_start,
              pageEnd: event.page_end,
              excerpt: event.excerpt,
            });
            useChatStore.getState().setCitations(bookId, [...currentCitations]);
            break;

          case "not_covered":
            useChatStore.getState().setNotCovered(bookId, event.text);
            break;

          case "error":
            setError(event.text);
            break;

          case "done":
            break;
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to get answer");
    } finally {
      setStreaming(false);
      inputRef.current?.focus();
      await rollUpIfNeeded();
    }
  }, [input, streaming, bookId, rollUpIfNeeded]);

  // Clearing is destructive, so it takes two taps: the first asks, the second
  // acts, and the prompt resets itself if left alone.
  useEffect(() => {
    if (!confirmClear) return;
    const timer = setTimeout(() => setConfirmClear(false), 3000);
    return () => clearTimeout(timer);
  }, [confirmClear]);

  const handleClearChat = useCallback(() => {
    if (!confirmClear) {
      setConfirmClear(true);
      return;
    }
    useChatStore.getState().resetChat(bookId);
    setConfirmClear(false);
    setError(null);
  }, [confirmClear, bookId]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        sendQuestion();
      }
    },
    [sendQuestion],
  );

  const handleCitationClick = useCallback(
    (citation: Citation) => {
      if (!citation.pageStart) return;
      onCitationClick?.({ page: citation.pageStart, text: citation.excerpt });
    },
    [onCitationClick],
  );

  return (
    <div className={cn("flex flex-col h-full", className)}>
      {/* Empty state */}
      {messages.length === 0 && !error && (
        <div className="flex-1 flex flex-col items-center justify-center px-6 text-center">
          <MessageSquare className="h-8 w-8 text-text-subtle mb-3" />
          <p className="text-body text-text-muted mb-1">
            Ask a question about this book
          </p>
          <p className="text-body-sm text-text-subtle max-w-[200px]">
            Answers are grounded in the book&apos;s content with source citations.
          </p>
        </div>
      )}

      {/* Thread header with the clear action */}
      {messages.length > 0 && (
        <div className="flex items-center justify-between border-b border-border-subtle px-3 py-1.5">
          <span className="text-body-sm text-text-subtle">Chat</span>
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
            {confirmClear ? "Confirm clear" : "Clear chat"}
          </button>
        </div>
      )}

      {/* Message thread */}
      {messages.length > 0 && (
        <div className="flex-1 overflow-y-auto px-3 py-4 space-y-4">
          {messages.map((msg, i) => (
            <div
              key={i}
              className={cn(
                "flex",
                msg.role === "user" ? "justify-end" : "justify-start",
              )}
            >
              <div
                className={cn(
                  "max-w-[85%] rounded-lg px-3 py-2 text-body-sm",
                  msg.role === "user"
                    ? "bg-accent/15 text-text-primary rounded-br-sm"
                    : "bg-bg-elevated text-text-primary rounded-bl-sm",
                )}
              >
                {/* Not covered message */}
                {"notCovered" in msg && msg.notCovered && (
                  <p className="text-text-muted italic mb-1">{msg.notCovered}</p>
                )}

                {/* Token text */}
                {"text" in msg && msg.text && (
                  <p className="whitespace-pre-wrap">{msg.text}</p>
                )}

                {/* Citations */}
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

          {/* Streaming indicator */}
          {streaming && (
            <div className="flex justify-start">
              <div className="bg-bg-elevated rounded-lg rounded-bl-sm px-3 py-2">
                <Loader variant="dots" />
              </div>
            </div>
          )}

          <div ref={bottomRef} />
        </div>
      )}

      {/* Error banner */}
      {error && (
        <div className="px-3 py-2 bg-state-error/10 border-t border-state-error/20">
          <p className="text-body-sm text-state-error">{error}</p>
        </div>
      )}

      {/* Input bar */}
      <div className="shrink-0 border-t border-border-subtle p-3">
        <div className="flex items-end gap-2 bg-bg-base rounded-lg border border-border p-2 focus-within:border-accent/50 transition-colors">
          <textarea
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask a question about this book…"
            rows={1}
            disabled={streaming}
            className="flex-1 bg-transparent text-body-sm text-text-primary placeholder-text-subtle resize-none outline-none min-h-[24px] max-h-[120px] disabled:opacity-50"
          />
          <button
            onClick={sendQuestion}
            disabled={!input.trim() || streaming}
            className="flex items-center justify-center w-8 h-8 rounded-md bg-accent text-white hover:bg-accent-hover transition-colors disabled:opacity-30 disabled:cursor-not-allowed shrink-0"
          >
            <Send className="h-3.5 w-3.5" strokeWidth={1.5} />
          </button>
        </div>
      </div>
    </div>
  );
}