"use client";

import { useEffect, useState } from "react";

/**
 * Full-screen loading state with a spinner and rotating messages. Used when
 * opening a book so the wait communicates progress ("Loading book…",
 * "Loading chat…") instead of a single static label.
 */
export function LoadingScreen({ messages }: { messages: string[] }) {
  const [index, setIndex] = useState(0);

  useEffect(() => {
    if (messages.length <= 1) return;
    const timer = setInterval(() => {
      setIndex((current) => (current + 1) % messages.length);
    }, 1400);
    return () => clearInterval(timer);
  }, [messages.length]);

  return (
    <div className="flex h-screen flex-col items-center justify-center gap-6 bg-bg-base">
      <div
        className="h-10 w-10 animate-spin rounded-full border-2 border-border border-t-accent"
        aria-hidden
      />
      <p
        key={index}
        className="text-body text-text-muted transition-opacity duration-300"
        role="status"
        aria-live="polite"
      >
        {messages[index]}
      </p>
    </div>
  );
}
