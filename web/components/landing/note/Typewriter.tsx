"use client";

import { useEffect, useState } from "react";

export function useTypewriter(
  text: string,
  { start, cps = 38, reduced = false }: { start: boolean; cps?: number; reduced?: boolean },
) {
  const [n, setN] = useState(reduced ? text.length : 0);
  useEffect(() => {
    if (reduced) {
      setN(text.length);
      return;
    }
    if (!start) {
      setN(0);
      return;
    }
    let i = 0;
    const id = setInterval(() => {
      i += 1;
      setN(i);
      if (i >= text.length) clearInterval(id);
    }, 1000 / cps);
    return () => clearInterval(id);
  }, [text, start, reduced, cps]);
  return n;
}

export function Typewriter({
  text,
  start,
  reduced,
  cps,
}: {
  text: string;
  start: boolean;
  reduced?: boolean;
  cps?: number;
}) {
  const n = useTypewriter(text, { start, reduced, cps });
  return (
    <>
      <span aria-hidden="true">
        {text.slice(0, n)}
        <span className="invisible">{text.slice(n)}</span>
      </span>
      <span className="sr-only">{text}</span>
    </>
  );
}
