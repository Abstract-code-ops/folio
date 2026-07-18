"use client";

import { useState, useRef, useCallback, useEffect } from "react";
import {
  Send,
  Loader2,
  MessageSquare,
  ExternalLink,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { apiClient } from "@/lib/api-client";
import type { QaEvent } from "@/types/chat";

// ── Message types ────────────────────────────────────────────

interface UserMessage {
  role: "user";
  text: string;
}

interface AiMessage {
  role: "ai";
  text: string;
  citations: Citation[];
  notCovered: string | null;
}

interface Citation {
  sectionHeading: string;
  pageStart: number | null;
  pageEnd: number | null;
  excerpt: string;
}

type Message = UserMessage | AiMessage;

// ── Component ────────────────────────────────────────────────

export interface ChatPanelProps {
  bookId: string;
  /** Called when a citation is clicked — parent navigates the PDF reader */
  onNavigateToPage?: (page: number) => void;
  className?: string;
}

export function ChatPanel({ bookId, onNavigateToPage, className }: ChatPanelProps) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  // Auto-scroll on new messages
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const sendQuestion = useCallback(async () => {
    const q = input.trim();
    if (!q || streaming) return;
    setInput("");
    setError(null);

    // Add user message
    const userMsg: UserMessage = { role: "user", text: q };
    setMessages((prev) => [...prev, userMsg]);

    // Add placeholder AI message
    const aiMsg: AiMessage = {
      role: "ai",
      text: "",
      citations: [],
      notCovered: null,
    };
    setMessages((prev) => [...prev, aiMsg]);
    setStreaming(true);

    let currentCitations: Citation[] = [];
    let currentText = "";

    try {
      const stream = await apiClient.askQuestion(bookId, q);
      const reader = stream.getReader();
      const decoder = new TextDecoder();

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const event = value as QaEvent;

        switch (event.type) {
          case "token":
            currentText += event.text;
            setMessages((prev) => {
              const copy = [...prev];
              const last = copy[copy.length - 1];
              if (last?.role === "ai") {
                (last as AiMessage).text = currentText;
              }
              return copy;
            });
            break;

          case "citation":
            currentCitations.push({
              sectionHeading: event.section_heading,
              pageStart: event.page_start,
              pageEnd: event.page_end,
              excerpt: event.excerpt,
            });
            setMessages((prev) => {
              const copy = [...prev];
              const last = copy[copy.length - 1];
              if (last?.role === "ai") {
                (last as AiMessage).citations = [...currentCitations];
              }
              return copy;
            });
            break;

          case "not_covered":
            setMessages((prev) => {
              const copy = [...prev];
              const last = copy[copy.length - 1];
              if (last?.role === "ai") {
                (last as AiMessage).notCovered = event.text;
              }
              return copy;
            });
            break;

          case "error":
            setError(event.text);
            break;

          case "done":
            // Streaming complete — no action needed
            break;
        }
      }
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to get answer",
      );
    } finally {
      setStreaming(false);
      inputRef.current?.focus();
    }
  }, [input, streaming, bookId]);

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
                <Loader2 className="h-4 w-4 text-text-muted animate-spin" />
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