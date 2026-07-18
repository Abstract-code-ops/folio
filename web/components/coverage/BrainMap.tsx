"use client";

import { useMemo, useState } from "react";
import { cn } from "@/lib/utils";
import type { SectionCoverage, ChapterNode } from "./types";
import {
  COVERAGE_COLORS,
  COVERAGE_GLOW,
  LEGEND_ITEMS,
  BRAIN_VIEWBOX,
  BRAIN_SHAPE,
  BRAIN_OUTLINE_STROKE,
  BRAIN_DIVIDE_STROKE,
  CHAPTER_NODE,
  CHAPTER_LINK,
} from "./config";
import { getBumpyBrainOutlinePoints, smoothClosedPathFromPoints, BRAIN_SULCUS_PATH } from "./brainShape";
import { aggregateSectionsToChapters } from "./aggregateChapters";
import { AmbientNetwork } from "./AmbientNetwork";

export interface BrainMapProps {
  sections: SectionCoverage[];
  /** Fires when a chapter node is activated (click or keyboard). Node
   * granularity is per-chapter now, so this replaces the old
   * `onSectionClick(sectionId)` callback — update the parent accordingly. */
  onChapterClick?: (chapter: { chapterIndex: number; sectionIds: string[] }) => void;
  className?: string;
}

export function BrainMap({ sections, onChapterClick, className }: BrainMapProps) {
  const [hoveredChapter, setHoveredChapter] = useState<number | null>(null);

  // Shape geometry is pure/static — computed once, reused by both the SVG
  // outline and the ambient canvas layer so they always line up.
  const outlinePoints = useMemo(() => getBumpyBrainOutlinePoints(BRAIN_SHAPE), []);
  const outlinePath = useMemo(() => smoothClosedPathFromPoints(outlinePoints), [outlinePoints]);

  const chapters: ChapterNode[] = useMemo(() => aggregateSectionsToChapters(sections), [sections]);

  const positions = useMemo(() => {
    const centerX = BRAIN_VIEWBOX.minX + BRAIN_VIEWBOX.width / 2;
    const centerY = BRAIN_VIEWBOX.minY + BRAIN_VIEWBOX.height / 2;
    const radiusX = BRAIN_VIEWBOX.width / 2;
    const radiusY = BRAIN_VIEWBOX.height / 2;
    const total = chapters.length;

    return chapters.map((chapter, i) => {
      const isLeft = i % 2 === 0;
      const hemiX = isLeft
        ? centerX - radiusX * CHAPTER_NODE.hemisphereInset
        : centerX + radiusX * CHAPTER_NODE.hemisphereInset;
      const yFrac = total > 1 ? i / (total - 1) : 0.5;
      const y =
        centerY - radiusY * CHAPTER_NODE.verticalSpan + yFrac * radiusY * CHAPTER_NODE.verticalSpan * 2;
      const jitterX = Math.sin(i * 12.9) * radiusX * CHAPTER_NODE.jitter;
      const jitterY = Math.cos(i * 7.3) * radiusY * CHAPTER_NODE.jitter;
      return { chapter, x: hemiX + jitterX, y: y + jitterY };
    });
  }, [chapters]);

  // Overall stats stay computed from the underlying sections (the true
  // grain of the data), even though the visual nodes are per-chapter.
  const totalSections = sections.length;
  const coveredSections = sections.filter((s) => s.coverage_score > 0).length;
  const pct = totalSections > 0 ? Math.round((coveredSections / totalSections) * 100) : 0;

  const hovered = positions.find((p) => p.chapter.chapterIndex === hoveredChapter) ?? null;

  function activateChapter(chapter: ChapterNode) {
    onChapterClick?.({ chapterIndex: chapter.chapterIndex, sectionIds: chapter.sectionIds });
  }

  return (
    <div className={cn("relative w-full", className)}>
      {/* Stats header */}
      <div className="px-4 py-3 border-b border-border-subtle">
        <div className="flex items-center justify-between">
          <span className="font-heading text-body-sm font-semibold text-text-primary">Coverage</span>
          <span className="text-body-sm text-text-muted">
            {coveredSections}/{totalSections} sections — {pct}%
          </span>
        </div>
        {/* Legend — unchanged */}
        <div className="flex items-center gap-3 mt-2">
          {LEGEND_ITEMS.map(({ label, state }) => (
            <div key={label} className="flex items-center gap-1.5">
              <div className="w-2 h-2 rounded-full" style={{ backgroundColor: COVERAGE_COLORS[state] }} />
              <span className="text-body-sm text-text-subtle">{label}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Brain visualization */}
      <div className="relative p-4">
        <div
          className="relative w-full"
          style={{ aspectRatio: `${BRAIN_VIEWBOX.width} / ${BRAIN_VIEWBOX.height}` }}
        >
          {/* Background: ambient decorative network (canvas) */}
          <AmbientNetwork viewBox={BRAIN_VIEWBOX} outlinePoints={outlinePoints} />

          {/* Foreground: brain outline + real coverage nodes (SVG, interactive) */}
          <svg
            viewBox={`${BRAIN_VIEWBOX.minX} ${BRAIN_VIEWBOX.minY} ${BRAIN_VIEWBOX.width} ${BRAIN_VIEWBOX.height}`}
            className="absolute inset-0 w-full h-full"
            xmlns="http://www.w3.org/2000/svg"
          >
            <path d={outlinePath} fill="none" stroke={BRAIN_OUTLINE_STROKE} strokeWidth={1.5} opacity={0.6} />
            <path
              d={BRAIN_SULCUS_PATH}
              fill="none"
              stroke={BRAIN_OUTLINE_STROKE}
              strokeWidth={1.5}
              opacity={0.6}
            />
            <line
              x1={150}
              y1={40}
              x2={150}
              y2={335}
              stroke={BRAIN_DIVIDE_STROKE}
              strokeWidth={0.5}
              strokeDasharray="4 4"
              opacity={0.3}
            />

            {/* Chapter-to-chapter connections — brighter than the ambient
                background, and dimmer wherever the two chapters they join
                are less covered on average. */}
            {positions.slice(1).map((curr, i) => {
              const prev = positions[i];
              const avg =
                (prev.chapter.coverageScore + curr.chapter.coverageScore) / (2 * CHAPTER_LINK.maxScore);
              const opacity =
                CHAPTER_LINK.minOpacity +
                Math.min(1, Math.max(0, avg)) * (CHAPTER_LINK.maxOpacity - CHAPTER_LINK.minOpacity);
              return (
                <line
                  key={`link-${curr.chapter.chapterIndex}`}
                  x1={prev.x}
                  y1={prev.y}
                  x2={curr.x}
                  y2={curr.y}
                  stroke={CHAPTER_LINK.color}
                  strokeWidth={CHAPTER_LINK.strokeWidth}
                  opacity={opacity}
                />
              );
            })}

            {/* Chapter nodes */}
            {positions.map(({ chapter, x, y }) => {
              const color = COVERAGE_COLORS[chapter.coverageState];
              const glow = COVERAGE_GLOW[chapter.coverageState];
              const isHovered = hoveredChapter === chapter.chapterIndex;
              const r = CHAPTER_NODE.radius * (isHovered ? CHAPTER_NODE.hoverScale : 1);

              return (
                <g key={chapter.chapterIndex}>
                  {glow !== "none" && (
                    <circle
                      cx={x}
                      cy={y}
                      r={r * 2.2}
                      fill="none"
                      stroke={color}
                      strokeWidth={0.6}
                      opacity={isHovered ? 0.35 : 0.15}
                      className={cn(
                        "coverage-transition",
                        chapter.coverageState === "well_covered" && "animate-pulse",
                      )}
                    />
                  )}
                  <circle
                    cx={x}
                    cy={y}
                    r={r}
                    fill={color}
                    opacity={isHovered ? 1 : 0.9}
                    stroke={isHovered ? color : "none"}
                    strokeWidth={1}
                    className="coverage-transition cursor-pointer"
                    role="button"
                    tabIndex={0}
                    aria-label={`${chapter.heading}, ${chapter.coverageState.replace("_", " ")}`}
                    onMouseEnter={() => setHoveredChapter(chapter.chapterIndex)}
                    onMouseLeave={() => setHoveredChapter(null)}
                    onFocus={() => setHoveredChapter(chapter.chapterIndex)}
                    onBlur={() => setHoveredChapter(null)}
                    onClick={() => activateChapter(chapter)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        activateChapter(chapter);
                      }
                    }}
                  />
                </g>
              );
            })}
          </svg>
        </div>

        {/* Tooltip — heading, page range, score. Nothing else. */}
        {hovered && (
          <div className="absolute bottom-4 left-4 right-4 bg-bg-elevated border border-border rounded-lg p-3 text-body-sm">
            <p className="font-heading font-semibold text-text-primary truncate">{hovered.chapter.heading}</p>
            <div className="flex items-center gap-3 mt-1 text-text-muted">
              <span>
                pp. {hovered.chapter.pageStart}–{hovered.chapter.pageEnd}
              </span>
              <span className="font-medium">
                Score: {hovered.chapter.coverageScore}/{CHAPTER_LINK.maxScore}
              </span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
