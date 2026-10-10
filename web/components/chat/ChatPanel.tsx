"use client";

import { useState, useRef, useCallback, useEffect } from "react";
import {
  Send,
  MessageSquare,
  ExternalLink,
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
  /** Called when a citation is clicked — parent navigates the PDF reader */
  onNavigateToPage?: (page: number) => void;
  className?: string;
}

export function ChatPanel({ bookId, onNavigateToPage, className }: ChatPanelProps) {
  const messages = useChatStore((s) => s.chats[bookId]?.messages ?? EMPTY_MESSAGES);
  const summary = useChatStore((s) => s.chats[bookId]?.summary ?? null);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  // Auto-scroll on new messages
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Fold the oldest messages (beyond the recent window) into the summary,
  // leaving the recent messages intact.
  const rollUpIfNeeded = useCallback(async () => {
    const store = useChatStore.getState();
    const chat = store.getChat(bookId);
    if (chat.messages.length <= MAX_VISIBLE) return;

    const overflow = chat.messages.length - RECENT_KEEP;
    const toSummarize = chat.messages.slice(0, overflow);

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
        store.setSummary(bookId, newSummary);
        store.dropOldest(bookId, overflow);
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

    // Conversation history (summary + recent messages) before this turn.
    const history: { role: string; content: string }[] = [];
    for (const m of chat.messages) {
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
      if (citation.pageStart && onNavigateToPage) {
        onNavigateToPage(citation.pageStart);
      }
    },
    [onNavigateToPage],
  );

  return (
    <div className={cn("flex flex-col h-full", className)}>
      {/* Empty state */}
      {messages.length === 0 && !summary && !error && (
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

      {/* Message thread */}
      {(messages.length > 0 || summary) && (
        <div className="flex-1 overflow-y-auto px-3 py-4 space-y-4">
          {summary && (
            <div className="rounded-lg bg-bg-elevated border border-border-subtle px-3 py-2">
              <p className="text-body-sm text-text-subtle mb-0.5">Earlier in this chat</p>
              <p className="text-body-sm text-text-muted">{summary}</p>
            </div>
          )}
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