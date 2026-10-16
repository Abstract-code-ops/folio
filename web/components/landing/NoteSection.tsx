"use client";

import { useRef } from "react";
import { motion, useInView, useReducedMotion, useScroll, useSpring } from "framer-motion";
import { cn } from "@/lib/utils";
import { PaperSurface } from "./note/PaperSurface";
import { SceneFrame } from "./note/scenes/SceneFrame";
import { sceneRegistry, SceneFallback } from "./note/scenes";
import { HandwrittenText } from "./note/HandwrittenText";
import { useTypewriter } from "./note/Typewriter";

type Segment = { text: string; highlight: boolean };
type Beat = { id: string; label: string; marginNote: string; segments: Segment[] };
export type NoteData = {
  name: string;
  photo: string;
  signature: string;
  beats: Beat[];
};

const EASE: [number, number, number, number] = [0.22, 1, 0.36, 1];

function fade(delay: number) {
  return {
    hidden: { opacity: 0, y: 8 },
    visible: {
      opacity: 1,
      y: 0,
      transition: { duration: 0.5, delay, ease: EASE },
    },
  };
}

// Types the full paragraph, highlighting the ==phrase== with a stable CSS
// highlighter (inline, so it can't drift like a positioned SVG annotation).
function Paragraph({
  segments,
  isFirst,
  start,
  reduced,
}: {
  segments: Segment[];
  isFirst: boolean;
  start: boolean;
  reduced: boolean;
}) {
  const fullText = segments.map((s) => s.text).join("");
  let hlStart = 0;
  let hlLen = 0;
  for (const s of segments) {
    if (s.highlight) {
      hlLen = s.text.length;
      break;
    }
    hlStart += s.text.length;
  }
  const hlEnd = hlStart + hlLen;
  const n = useTypewriter(fullText, { start, cps: 65, reduced });

  const before = fullText.slice(0, Math.min(n, hlStart));
  const hl = n > hlStart ? fullText.slice(hlStart, Math.min(n, hlEnd)) : "";
  const after = n > hlEnd ? fullText.slice(hlEnd, n) : "";
  const rest = fullText.slice(n);

  return (
    <p
      className={cn(
        "mt-4 max-w-[65ch] font-body text-body-lg leading-relaxed text-text-primary",
        isFirst && "drop-cap",
      )}
    >
      <span aria-hidden="true">
        {before}
        {hl && <span className="highlight-mark">{hl}</span>}
        {after}
        <span className="invisible">{rest}</span>
      </span>
      <span className="sr-only">{fullText}</span>
    </p>
  );
}

function Arrow() {
  return (
    <svg
      viewBox="0 0 24 24"
      className="h-4 w-4 shrink-0 text-accent"
      fill="none"
      aria-hidden="true"
    >
      <path
        d="M3 20 C 9 14, 15 8, 21 3 M15 3 h6 v6"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function RibbonTail() {
  return (
    <svg viewBox="0 0 10 40" className="h-9 w-2.5 text-accent" aria-hidden="true">
      <path d="M2.5 0 H7.5 V31 L5 38 L2.5 31 Z" fill="currentColor" />
    </svg>
  );
}

function Beat({ beat, index, isFirst }: { beat: Beat; index: number; isFirst: boolean }) {
  const reduced = useReducedMotion() ?? false;
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInView(ref, { once: true, margin: "0px 0px -20% 0px" });
  const Scene = sceneRegistry[beat.id] ?? SceneFallback;
  const show = reduced || inView;

  return (
    <div ref={ref} className="relative flex gap-6">
      <div className="w-5 shrink-0">
        <div className="absolute left-[10px] top-3 h-2 w-2 -translate-x-1/2 rounded-full bg-accent" />
      </div>

      <div className="relative min-w-0 flex-1">
        <motion.h3
          className="font-body text-h4"
          initial={reduced ? false : "hidden"}
          animate={show ? "visible" : "hidden"}
          variants={fade(0)}
        >
          <span className="mr-3 font-body text-h3 text-text-subtle">{index + 1}</span>
          <span className="text-text-primary">{beat.label}</span>
        </motion.h3>

        <Paragraph segments={beat.segments} isFirst={isFirst} start={inView} reduced={reduced} />

        <motion.div
          className="mt-6 h-24 sm:h-28"
          initial={reduced ? false : "hidden"}
          animate={show ? "visible" : "hidden"}
          variants={fade(0.4)}
        >
          <SceneFrame seed={4 + index}>
            <Scene />
          </SceneFrame>
        </motion.div>

        {beat.marginNote && (
          <motion.div
            className="mt-4 flex items-center gap-2 md:absolute md:left-full md:top-10 md:mt-0 md:w-44 md:-rotate-[1.5deg] md:pl-8"
            initial={reduced ? false : "hidden"}
            animate={show ? "visible" : "hidden"}
            variants={fade(0.8)}
          >
            <Arrow />
            <HandwrittenText text={beat.marginNote} size={16} start={inView} className="text-text-muted" />
          </motion.div>
        )}
      </div>
    </div>
  );
}

function Bookplate({
  name,
  photo,
  signature,
}: {
  name: string;
  photo: string;
  signature: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInView(ref, { once: true, margin: "0px 0px -10% 0px" });
  return (
    <div ref={ref} className="flex flex-wrap items-center gap-6">
      <div className="rounded-sm border-2 border-double border-border px-5 py-3">
        <span className="font-body text-body-sm uppercase tracking-[0.15em] text-text-muted">
          From the shelf of {name}
        </span>
      </div>
      {photo && (
        <div className="h-12 w-12 overflow-hidden rounded-full border border-border bg-bg-elevated">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={photo} alt="" className="h-full w-full object-cover" />
        </div>
      )}
      <HandwrittenText text={signature} size={36} start={inView} rotate={-2} className="text-text-primary" />
    </div>
  );
}

export function NoteSection({ name, photo, signature, beats }: NoteData) {
  const reduced = useReducedMotion() ?? false;
  const sectionRef = useRef<HTMLElement>(null);
  const { scrollYProgress } = useScroll({
    target: sectionRef,
    offset: ["start end", "end end"],
  });
  const scaleY = useSpring(scrollYProgress, { stiffness: 90, damping: 25 });

  return (
    <section id="about" ref={sectionRef} className="border-y border-border-subtle">
      <PaperSurface className="py-24">
        <div className="mx-auto max-w-5xl px-6">
          <div className="flex items-baseline justify-between border-b border-border pb-3">
            <span className="font-heading text-body-sm text-text-subtle">Why I built this</span>
            <span className="font-heading text-body-sm text-text-subtle">p. 1</span>
          </div>

          <div className="relative pt-12">
            <div className="absolute bottom-8 left-[10px] top-9 w-[2px] bg-border" />
            <motion.div
              className="absolute bottom-8 left-[10px] top-9 w-[2px] origin-top bg-accent"
              style={{ scaleY: reduced ? 1 : scaleY }}
            />
            <div className="absolute -top-2 left-[10px] -translate-x-1/2">
              <RibbonTail />
            </div>

            <div className="space-y-20 md:space-y-28">
              {beats.map((beat, i) => (
                <Beat key={beat.id} beat={beat} index={i} isFirst={i === 0} />
              ))}
            </div>
          </div>

          <div className="mt-20 flex flex-wrap items-center justify-between gap-8 border-t border-border pt-10">
            <Bookplate name={name} photo={photo} signature={signature} />
            <span className="font-heading text-body-sm text-text-subtle">p. 1</span>
          </div>
        </div>
      </PaperSurface>
    </section>
  );
}
