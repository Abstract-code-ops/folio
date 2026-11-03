"use client";

import UseAnimations from "react-useanimations";
import loading from "react-useanimations/lib/loading";

/**
 * Small looping "thinking" indicator built from a useAnimations (MIT) icon.
 *
 * `react-useanimations` follows the current text color automatically, so
 * `text-accent` on the wrapper tints it to the app accent in both themes, and it
 * respects prefers-reduced-motion on its own.
 */
export function ThinkingAnimation({ size = 20 }: { size?: number }) {
  return (
    <span className="inline-flex text-accent" aria-hidden="true">
      <UseAnimations animation={loading} size={size} />
    </span>
  );
}
