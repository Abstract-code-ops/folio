"use client";

import { useEffect, useState } from "react";
import { cn } from "@/lib/utils";

type Props = {
  text: string;
  size: number;
  start: boolean;
  rotate?: number;
  className?: string;
  color?: string;
};

// Animated handwriting via Tegaki (lazy-loaded). Renders reserved space first,
// then the writing layer over it; falls back to static Caveat if it fails.
export function HandwrittenText({ text, size, start, rotate, className, color }: Props) {
  const [mod, setMod] = useState<{ Renderer: any; font: any } | null>(null);

  useEffect(() => {
    if (!start || mod) return;
    let cancelled = false;
    Promise.all([import("tegaki"), import("tegaki/fonts/caveat")])
      .then(([{ TegakiRenderer }, caveat]) => {
        if (!cancelled) setMod({ Renderer: TegakiRenderer, font: caveat.default });
      })
      .catch(() => {
        /* stay on the static fallback */
      });
    return () => {
      cancelled = true;
    };
  }, [start, mod]);

  const hand: React.CSSProperties = { fontFamily: "var(--font-hand)" };

  return (
    <span
      className={cn("relative inline-block shrink-0 whitespace-nowrap min-w-max", className)}
      style={{ fontSize: size, color, transform: rotate ? `rotate(${rotate}deg)` : undefined }}
    >
      {/* reserved space for layout — invisible */}
      <span
        aria-hidden="true"
        style={{ ...hand, visibility: "hidden", whiteSpace: "nowrap", display: "inline-block" }}
      >
        {text}
      </span>

      {/* the writing layer */}
      <span className="absolute left-0 top-0" aria-hidden="true" style={{ whiteSpace: "nowrap" }}>
        {mod ? (
          <mod.Renderer
            font={mod.font}
            time={{ mode: "uncontrolled", loop: false }}
            reducedMotion="user"
            style={{ fontSize: size }}
          >
            {text}
          </mod.Renderer>
        ) : (
          <span style={hand}>{text}</span>
        )}
      </span>

      {/* full text for screen readers, exactly once */}
      <span className="sr-only">{text}</span>
    </span>
  );
}
