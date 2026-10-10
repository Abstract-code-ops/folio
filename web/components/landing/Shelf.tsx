"use client";

import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { cn } from "@/lib/utils";
import { landing } from "@/content/landing";

type Book = (typeof landing.shelf.books)[number];

// Cloth RGB values (mirror --spine-1..8) used to pick a contrasting text colour.
const SPINE_RGB: Record<number, [number, number, number]> = {
  1: [107, 42, 46],
  2: [38, 65, 143],
  3: [43, 43, 46],
  4: [232, 223, 200],
  5: [176, 106, 114],
  6: [90, 107, 122],
  7: [122, 106, 130],
  8: [194, 162, 90],
};

const LOOP_MS = 5500;
const PULL_EASE: [number, number, number, number] = [0.22, 1, 0.36, 1];

const BOOK_W = 200;
const BOOK_H = 300;
const BOOK_THICK = 40; // total thickness (cover at ±20px)

const PILE_W = 121;
const PILE_H = 26;
const PILE_T = 18; // page-block thickness

function isLightCloth(spine: number): boolean {
  const rgb = SPINE_RGB[spine] ?? [0, 0, 0];
  const lin = rgb.map((v) => {
    const c = v / 255;
    return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
  });
  return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2] > 0.5;
}

// A realistic hardback: front cover + striped fore-edge pages + back cover,
// resting at rotateY(-29deg) and returning to -15deg on hover.
function Book3D({ book }: { book: Book }) {
  const cloth = `rgb(var(--spine-${book.spine}))`;
  const light = isLightCloth(book.spine);
  const text = light ? "text-spine-ink" : "text-spine-paper";

  return (
    <div style={{ perspective: "600px", width: BOOK_W, height: BOOK_H }}>
      <motion.div
        className="relative"
        style={{ width: BOOK_W, height: BOOK_H, transformStyle: "preserve-3d" }}
        initial={{ rotateY: -15 }}
        animate={{ rotateY: -29 }}
        whileHover={{ rotateY: -15 }}
        transition={{ duration: 0.6, ease: "easeInOut" }}
      >
        {/* front cover */}
        <div
          className="spine-cloth"
          style={{
            position: "absolute",
            top: 0,
            left: 0,
            width: BOOK_W,
            height: BOOK_H,
            transform: `translateZ(${BOOK_THICK / 2}px)`,
            backgroundColor: cloth,
            boxShadow: "5px 5px 20px rgba(0,0,0,0.35)",
          }}
        >
          <div className={cn("flex h-full flex-col justify-between p-5", text)}>
            <div>
              <span className="block font-heading text-body-sm uppercase tracking-[0.2em] opacity-70">
                Folio
              </span>
              <span className="mt-2 block h-px w-8 bg-current opacity-50" />
            </div>
            <div className="font-body text-h4 leading-snug">{book.title}</div>
            <div className="font-body text-body-sm opacity-80">
              {book.subtitle}
            </div>
          </div>
        </div>

        {/* page block (fore-edge, right) */}
        <div
          style={{
            position: "absolute",
            left: 0,
            top: 3,
            width: 38,
            height: BOOK_H - 6,
            transform: "translateX(177px) rotateY(90deg)",
            backgroundImage:
              "repeating-linear-gradient(90deg, rgb(var(--spine-paper)) 0 2px, rgb(255 255 255) 2px 4px)",
          }}
        />

        {/* back cover */}
        <div
          style={{
            position: "absolute",
            top: 0,
            left: 0,
            width: BOOK_W,
            height: BOOK_H,
            transform: `translateZ(${-BOOK_THICK / 2}px)`,
            backgroundColor: cloth,
            boxShadow: "-10px 0 50px 10px rgba(0,0,0,0.35)",
          }}
        />
      </motion.div>
    </div>
  );
}

// A mini 3D book for the pile — same cover + page-block + back construction as
// the featured book, with a slight per-book rotation for a natural pile.
function PileBook({
  book,
  index,
  active,
}: {
  book: Book;
  index: number;
  active: boolean;
}) {
  const cloth = `rgb(var(--spine-${book.spine}))`;
  const light = isLightCloth(book.spine);
  const text = light ? "text-spine-ink" : "text-spine-paper";
  const tilt = -20 + (index % 3) * 2; // -20, -18, -16 — slight variation

  return (
    <div style={{ perspective: "500px", width: PILE_W, height: PILE_H }}>
      <div
        style={{
          position: "relative",
          width: PILE_W,
          height: PILE_H,
          transformStyle: "preserve-3d",
          transform: `rotateY(${tilt}deg) rotateX(6deg)`,
          opacity: active ? 0.3 : 1,
          transition: "opacity 0.5s ease",
        }}
      >
        {/* front cover */}
        <div
          className="spine-cloth"
          style={{
            position: "absolute",
            inset: 0,
            transform: `translateZ(${PILE_T / 2}px)`,
            backgroundColor: cloth,
            borderRadius: 3,
            boxShadow: "3px 3px 10px rgba(0,0,0,0.3)",
          }}
        >
          <span
            className={cn(
              "absolute inset-x-0 top-1/2 -translate-y-1/2 px-2 font-heading text-body-sm",
              text,
            )}
          >
            {book.label}
          </span>
        </div>

        {/* page block (fore-edge, right) */}
        <div
          style={{
            position: "absolute",
            left: 0,
            top: 3,
            width: PILE_T,
            height: PILE_H - 6,
            transform: `translateX(${PILE_W - PILE_T / 2 - 4}px) rotateY(90deg)`,
            backgroundImage:
              "repeating-linear-gradient(90deg, rgb(var(--spine-paper)) 0 1px, rgb(255 255 255) 1px 2px)",
          }}
        />

        {/* back cover */}
        <div
          style={{
            position: "absolute",
            inset: 0,
            transform: `translateZ(${-PILE_T / 2}px)`,
            backgroundColor: cloth,
          }}
        />
      </div>
    </div>
  );
}

function Pile({ books, active }: { books: Book[]; active: number }) {
  return (
    <div className="flex flex-col" style={{ gap: 2 }}>
      {books.map((b, i) => (
        <PileBook key={b.title} book={b} index={i} active={i === active} />
      ))}
    </div>
  );
}

export function Shelf() {
  const reduced = useReducedMotion() ?? false;
  const books = landing.shelf.books;
  const [active, setActive] = useState(0);
  const paused = useRef(false);
  const rootRef = useRef<HTMLDivElement>(null);

  // Cycle the featured book.
  useEffect(() => {
    if (reduced || books.length <= 1) return;
    const id = setInterval(() => {
      if (paused.current) return;
      setActive((p) => (p + 1) % books.length);
    }, LOOP_MS);
    return () => clearInterval(id);
  }, [reduced, books.length]);

  // Pause when the hero leaves the viewport.
  useEffect(() => {
    if (reduced) return;
    const el = rootRef.current;
    if (!el) return;
    const obs = new IntersectionObserver(
      ([entry]) => (paused.current = !entry.isIntersecting),
      { threshold: 0.2 },
    );
    obs.observe(el);
    return () => obs.disconnect();
  }, [reduced]);

  // Pause when the tab is hidden.
  useEffect(() => {
    if (reduced) return;
    const onVis = () => (paused.current = document.hidden);
    document.addEventListener("visibilitychange", onVis);
    return () => document.removeEventListener("visibilitychange", onVis);
  }, [reduced]);

  const book = books[active];

  return (
    <div
      ref={rootRef}
      className="flex flex-col items-center gap-10 sm:flex-row sm:items-end sm:justify-center sm:gap-16"
      aria-hidden="true"
    >
      <Pile books={books} active={active} />

      <div
        className="relative flex items-center justify-center"
        style={{ width: BOOK_W, height: BOOK_H }}
      >
        <AnimatePresence mode="wait">
          <motion.div
            key={book.title}
            style={{ perspective: "600px" }}
            initial={reduced ? false : { x: -220, y: 90, opacity: 0, scale: 0.65 }}
            animate={{ x: 0, y: 0, opacity: 1, scale: 1 }}
            exit={reduced ? undefined : { x: -220, y: 90, opacity: 0, scale: 0.65 }}
            transition={{ duration: reduced ? 0 : 0.7, ease: PULL_EASE }}
          >
            <Book3D book={book} />
          </motion.div>
        </AnimatePresence>
      </div>
    </div>
  );
}
