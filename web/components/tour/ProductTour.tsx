"use client";

// Lightweight first-visit tour (driver.js). Non-blocking, dismissible, and
// remembered in localStorage so it shows once per page. Steps whose target
// isn't in the DOM are skipped (e.g. desktop-only panels on mobile).

import { useEffect } from "react";
import { driver } from "driver.js";
import "driver.js/dist/driver.css";

export type TourPage = "library" | "reader";

interface Step {
  element: string;
  title: string;
  description: string;
}

const STEPS: Record<TourPage, Step[]> = {
  library: [
    {
      element: "[data-tour='tour-search']",
      title: "Find a book",
      description: "Search the shelf by title or author.",
    },
    {
      element: "[data-tour='tour-categories']",
      title: "Browse by category",
      description: "Filter by subject — Mathematics, Computer Science, and more.",
    },
    {
      element: "[data-tour='tour-grid']",
      title: "Open a book",
      description: "Pick any book to read it and ask it questions.",
    },
  ],
  reader: [
    {
      element: "[data-tour='tour-pdf']",
      title: "The page",
      description:
        "Select any passage to ask about it, or save it straight to a note.",
    },
    {
      element: "[data-tour='tour-panel']",
      title: "Chat & notes",
      description:
        "Ask questions — answers cite the pages they used — and build notes as you read.",
    },
  ],
};

export function ProductTour({ page }: { page: TourPage }) {
  useEffect(() => {
    if (typeof window === "undefined") return;
    const key = `folio-tour-${page}`;
    if (localStorage.getItem(key)) return;

    const steps = STEPS[page]
      .filter((s) => document.querySelector(s.element))
      .map((s) => ({
        element: s.element,
        popover: { title: s.title, description: s.description },
      }));
    if (steps.length === 0) return;

    const tour = driver({
      showProgress: true,
      allowClose: true,
      overlayColor: "rgba(0, 0, 0, 0.55)",
      nextBtnText: "Next",
      prevBtnText: "Back",
      doneBtnText: "Got it",
      steps,
      onDestroyed: () => localStorage.setItem(key, "1"),
    });

    // Defer so the page paints before driver measures element positions.
    const timer = setTimeout(() => tour.drive(), 700);
    return () => clearTimeout(timer);
  }, [page]);

  return null;
}
