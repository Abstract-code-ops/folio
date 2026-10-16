"use client";

import { useId, useRef } from "react";
import { motion, useInView, useReducedMotion } from "framer-motion";

export const EASE = [0.22, 1, 0.36, 1] as const;

export const strokeVariants = {
  hidden: { pathLength: 0 },
  visible: {
    pathLength: 1,
    transition: { duration: 1.1, ease: EASE },
  },
};

export const fillVariants = {
  hidden: { opacity: 0 },
  visible: { opacity: 1, transition: { duration: 0.3 } },
};

export function rectPath(x: number, y: number, w: number, h: number): string {
  return `M ${x} ${y} H ${x + w} V ${y + h} H ${x} Z`;
}

// Shared SVG wrapper: wobble filter + a once-only stroke draw-in reveal.
export function SceneFrame({
  children,
  className,
  seed = 4,
}: {
  children: React.ReactNode;
  className?: string;
  seed?: number;
}) {
  const rawId = useId();
  const id = rawId.replace(/[^a-zA-Z0-9]/g, "");
  const ref = useRef<SVGSVGElement>(null);
  const inView = useInView(ref, { once: true, margin: "0px 0px -20% 0px" });
  const reduced = useReducedMotion();
  const show = reduced || inView;

  return (
    <motion.svg
      ref={ref}
      viewBox="0 0 260 200"
      className={className}
      initial={reduced ? "visible" : "hidden"}
      animate={show ? "visible" : "hidden"}
      aria-hidden="true"
      focusable="false"
      style={{ height: "100%" }}
    >
      <defs>
        <filter id={`wobble-${id}`} x="-5%" y="-5%" width="110%" height="110%">
          <feTurbulence
            type="fractalNoise"
            baseFrequency="0.035"
            numOctaves="2"
            seed={seed}
            result="n"
          />
          <feDisplacementMap in="SourceGraphic" in2="n" scale="3" />
        </filter>
      </defs>
      <g filter={`url(#wobble-${id})`}>{children}</g>
    </motion.svg>
  );
}
