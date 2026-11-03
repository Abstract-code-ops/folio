"use client";

import { useEffect, useState } from "react";
import Lottie from "lottie-react";

/**
 * Book page-flip loader (Lottie).
 *
 * The animation is served from `/public/animations/page-flipping.json` so it can
 * be swapped without a rebuild. Until that file exists (or when the visitor
 * prefers reduced motion) it falls back to the plain spinner, so nothing breaks
 * if the asset is missing.
 */
export function BookLoader({ className }: { className?: string }) {
  const [data, setData] = useState<object | null>(null);
  const [reduced, setReduced] = useState(false);

  useEffect(() => {
    if (typeof window !== "undefined" && window.matchMedia) {
      setReduced(window.matchMedia("(prefers-reduced-motion: reduce)").matches);
    }
    let alive = true;
    fetch("/animations/page-flipping.json")
      .then((res) => (res.ok ? res.json() : null))
      .then((json) => {
        if (alive) setData(json);
      })
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, []);

  if (reduced || !data) {
    return (
      <div
        className={
          "h-10 w-10 animate-spin rounded-full border-2 border-border border-t-accent " +
          (className ?? "")
        }
        aria-hidden
      />
    );
  }

  return (
    <Lottie
      animationData={data}
      loop
      autoplay
      style={{ width: 120, height: 120 }}
      aria-hidden
    />
  );
}
