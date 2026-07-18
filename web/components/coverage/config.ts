// Every tunable knob for the Brain Coverage Map lives in this one file.
// Change colors, shape, node density, or animation speed here without
// touching layout or rendering logic in the components.

import type { CoverageState } from "./types";

export const COVERAGE_COLORS: Record<CoverageState, string> = {
  uncovered: "#252528",
  mentioned: "#92400E",
  partial: "#D97706",
  well_covered: "#4ADE80",
};

export const COVERAGE_GLOW: Record<CoverageState, string> = {
  uncovered: "none",
  mentioned: "0 0 6px rgba(146, 64, 14, 0.4)",
  partial: "0 0 8px rgba(217, 119, 6, 0.5)",
  well_covered: "0 0 10px rgba(74, 222, 128, 0.5)",
};

export const LEGEND_ITEMS: { label: string; state: CoverageState }[] = [
  { label: "Well covered", state: "well_covered" },
  { label: "Partial", state: "partial" },
  { label: "Mentioned", state: "mentioned" },
  { label: "Not started", state: "uncovered" },
];

// ── Brain silhouette (SVG) ─────────────────────────────────────────
// Coordinate space shared by the outline, the chapter nodes, and the
// ambient canvas layer, so everything lines up regardless of render size.
export const BRAIN_VIEWBOX = { minX: -80, minY: 20, width: 460, height: 360 };

export const BRAIN_SHAPE = {
  bumpCount: 15, // number of gyri-like lobes around the perimeter
  bumpDepth: 6, // px, how far each bump pushes the boundary in/out
  secondaryWaveMix: 0.4, // 0–1, adds organic irregularity to the bumps
  samplesPerSegment: 10, // smoothness of the sampled outline before bumping
};

export const BRAIN_OUTLINE_STROKE = "#252528";
export const BRAIN_DIVIDE_STROKE = "#1C1C1F";

// ── Foreground: real chapter coverage nodes (SVG, interactive) ─────
export const CHAPTER_NODE = {
  radius: 7,
  hoverScale: 1.35,
  hemisphereInset: 0.55, // 0–1, how far each hemisphere's node column sits from center
  verticalSpan: 0.62, // 0–1, vertical spread of the node column
  jitter: 0.05, // organic per-node position jitter
};

export const CHAPTER_LINK = {
  color: "#A1A1AA",
  minOpacity: 0.3,
  maxOpacity: 0.85,
  strokeWidth: 1.4,
  maxScore: 15,
};

// ── Background: ambient decorative network (canvas, non-interactive) ─
// Purely visual texture — never tied to real coverage data.
export const AMBIENT_NETWORK = {
  seed: 1337,
  dotCount: 90,
  dotRadius: 1.3,
  dotColor: "#52525B",
  dotOpacity: 0.35,
  neighborsPerDot: 2,
  maxLinkDistance: 55,
  lineColor: "#3F3F46",
  lineOpacity: 0.15,
  insetMargin: 0.92, // keeps dots just inside the bumpy boundary
  pulse: {
    color: "#D4D4D8",
    radius: 1.8,
    durationMs: 550,
    spawnIntervalMs: 120,
    maxConcurrent: 5,
  },
};
