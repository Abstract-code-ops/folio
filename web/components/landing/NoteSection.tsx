"use client";

import { useEffect, useRef } from "react";
import { motion, useReducedMotion, useScroll, useSpring } from "framer-motion";
import { annotate } from "rough-notation";
import { cn } from "@/lib/utils";

type Segment = { text: string; highlight: boolean };
type Beat = { id: string; label: string; marginNote: string; segments: Segment[] };
export type NoteData = {
  name: string;
  photo: string;
  signature: string;
  beats: Beat[];
};

const EASE: [number, number, number, number] = [0.22, 1, 0.36, 1];

// Reads the current theme's accent from the CSS token at mount time.
function accent(alpha = 1): string {
  const raw =
    getComputedStyle(document.documentElement)
      .getPropertyValue("--accent")
      .trim() || "38 65 143";
  const rgb = raw.split(/\s+/).slice(0, 3).join(", ");
  return `rgba(${rgb}, ${alpha})`;
}

// A ==highlighted phrase==, drawn in by Rough Notation when ~60% in view.
function Highlight({ text }: { text: string }) {
  const ref = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ann = annotate(el, {
      type: "highlight",
      color: accent(0.22),
      padding: [2, 3],
      iterations: 1,
      animationDuration: 700,
    });
    let shown = false;
    const obs = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting && !shown) {
          shown = true;
          ann.show();
          obs.disconnect();
        }
      },
      { threshold: 0.6 },
    );
    obs.observe(el);
    return () => {
      obs.disconnect();
      ann.remove();
    };
  }, []);
  return <span ref={ref}>{text}</span>;
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

// Silk ribbon tail hanging from the top of the progress line.
function RibbonTail() {
  return (
    <svg viewBox="0 0 10 40" className="h-9 w-2.5 text-accent" aria-hidden="true">
      <path d="M2.5 0 H7.5 V31 L5 38 L2.5 31 Z" fill="currentColor" />
    </svg>
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
  return (
    <div className="flex flex-wrap items-center gap-6">
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
      <span
        className="-rotate-2 text-3xl text-text-primary"
        style={{ fontFamily: "var(--font-hand)" }}
      >
        {signature}
      </span>
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
    <section id="about" ref={sectionRef} className="bg-bg-surface">
      {/* running header */}
      <div className="mx-auto max-w-5xl px-6 pt-24">
        <div className="flex items-baseline justify-between border-b border-border pb-3">
          <span className="font-heading text-body-sm text-text-subtle">
            Why I built this
          </span>
          <span className="font-heading text-body-sm text-text-subtle">p. 1</span>
        </div>
      </div>

      {/* ribbon + beats */}
      <div className="mx-auto max-w-5xl px-6 pb-16 pt-12">
        <div className="relative">
          {/* ribbon track + fill */}
          <div className="absolute bottom-8 left-[10px] top-9 w-[2px] bg-border" />
          <motion.div
            className="absolute bottom-8 left-[10px] top-9 w-[2px] origin-top bg-accent"
            style={{ scaleY: reduced ? 1 : scaleY }}
          />
          {/* silk ribbon tail */}
          <div className="absolute -top-2 left-[10px] -translate-x-1/2">
            <RibbonTail />
          </div>

          <div className="space-y-20 md:space-y-28">
            {beats.map((beat, i) => (
              <motion.div
                key={beat.id}
                className="relative flex gap-6"
                initial={reduced ? false : { opacity: 0, y: 8 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, margin: "-10% 0px" }}
                transition={{ duration: 0.6, ease: EASE }}
              >
                {/* node dot on the ribbon */}
                <div className="w-5 shrink-0">
                  <div className="absolute left-[10px] top-3 h-2 w-2 -translate-x-1/2 rounded-full bg-accent" />
                </div>

                {/* beat content */}
                <div className="relative min-w-0 flex-1">
                  <h3 className="font-body text-h4">
                    <span className="mr-3 font-body text-h3 text-text-subtle">
                      {i + 1}
                    </span>
                    <span className="text-text-primary">{beat.label}</span>
                  </h3>

                  <p
                    className={cn(
                      "mt-4 max-w-[65ch] font-body text-body-lg leading-relaxed text-text-primary",
                      i === 0 && "drop-cap",
                    )}
                  >
                    {beat.segments.map((s, si) =>
                      s.highlight ? (
                        <Highlight key={si} text={s.text} />
                      ) : (
                        <span key={si}>{s.text}</span>
                      ),
                    )}
                  </p>

                  {/* margin note */}
                  {beat.marginNote && (
                    <div className="mt-4 flex items-center gap-2 md:absolute md:left-full md:top-10 md:mt-0 md:w-44 md:-rotate-[1.5deg] md:pl-8">
                      <Arrow />
                      <span
                        className="text-body-sm text-text-muted"
                        style={{ fontFamily: "var(--font-hand)" }}
                      >
                        {beat.marginNote}
                      </span>
                    </div>
                  )}
                </div>
              </motion.div>
            ))}
          </div>
        </div>
      </div>

      {/* closing: bookplate + signature */}
      <div className="mx-auto max-w-5xl px-6 pb-24">
        <div className="flex flex-wrap items-center justify-between gap-8 border-t border-border pt-10">
          <Bookplate name={name} photo={photo} signature={signature} />
          <span className="font-heading text-body-sm text-text-subtle">p. 1</span>
        </div>
      </div>
    </section>
  );
}
