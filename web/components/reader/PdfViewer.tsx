"use client";

import { useCallback, useEffect, useRef } from "react";
import {
  PDFViewer,
  type PluginRegistry,
  type ScrollCapability,
} from "@embedpdf/react-pdf-viewer";
import { cn } from "@/lib/utils";

export interface HighlightTarget {
  /** 1-based page the citation points at. */
  page: number;
  /** Text to find on that page — the citation's excerpt. */
  text: string;
}

export interface PdfViewerProps {
  url: string | null;
  pageNumber: number;
  onPageChange: (page: number) => void;
  /** Set when a chat citation is clicked; cleared or replaced on the next one. */
  highlight?: HighlightTarget | null;
  className?: string;
}

// ── EmbedPDF search plugin ────────────────────────────────────
// Declared locally rather than importing @embedpdf/plugin-search, which is a
// transitive dependency of the viewer preset: this is the whole surface used,
// and it keeps the dependency graph honest.

interface SearchResultLike {
  /** 0-based index of the page the match is on. */
  pageIndex: number;
}

interface SearchStateLike {
  results: SearchResultLike[];
}

interface SearchCapabilityLike {
  searchAllPages(keyword: string): { toPromise(): Promise<unknown> };
  getState(): SearchStateLike;
  setShowAllResults(showAll: boolean): void;
  goToResult(index: number): number;
}

/**
 * Candidate search phrases for an excerpt, longest first.
 *
 * The excerpt is truncated at 240 characters and the PDF's own text layer
 * differs from ours (line breaks, hyphenation), so a long phrase can miss.
 * Each candidate is tried in turn and the first one that lands on the right
 * page wins.
 */
function searchPhrases(text: string): string[] {
  const words = text
    .replace(/\.{3}$/, "")
    .replace(/\s+/g, " ")
    .trim()
    .split(" ")
    .filter(Boolean);

  const phrases: string[] = [];
  for (const size of [8, 5, 3]) {
    if (words.length >= size) {
      const phrase = words.slice(0, size).join(" ");
      if (!phrases.includes(phrase)) phrases.push(phrase);
    }
  }
  return phrases;
}

// Folio's interactive accent, injected into EmbedPDF's dark theme
const FOLIO_ACCENT = "#26418F";

export function PdfViewer({
  url,
  pageNumber,
  onPageChange,
  highlight,
  className,
}: PdfViewerProps) {
  const scrollRef = useRef<ScrollCapability | null>(null);
  const searchRef = useRef<SearchCapabilityLike | null>(null);
  const lastReportedPage = useRef<number | null>(null);

  // Proxy the PDF through Next.js so the WASM engine fetches it same-origin
  const proxiedUrl = url ? `/api/pdf?url=${encodeURIComponent(url)}` : null;

  // Wire EmbedPDF's scroll plugin to the parent's page state
  const handleReady = useCallback(
    (registry: PluginRegistry) => {
      const capability = registry
        .getPlugin("scroll")
        ?.provides?.() as ScrollCapability | undefined;
      if (capability) {
        scrollRef.current = capability;
        capability.onPageChange(({ pageNumber: p }) => {
          lastReportedPage.current = p;
          onPageChange(p);
        });
      }

      const search = registry
        .getPlugin("search")
        ?.provides?.() as SearchCapabilityLike | undefined;
      if (search) searchRef.current = search;
    },
    [onPageChange],
  );

  // External jump (coverage map click / skip-to-page): only when the page
  // change did not originate from the viewer's own scrolling
  useEffect(() => {
    if (lastReportedPage.current === pageNumber) return;
    scrollRef.current?.scrollToPage({ pageNumber, behavior: "smooth" });
  }, [pageNumber]);

  // Citation click: find the cited text and highlight every match, making the
  // one on the citation's page the active result. The page jump is handled by
  // the parent setting `pageNumber`, so a missed search still lands correctly.
  useEffect(() => {
    const search = searchRef.current;
    if (!search || !highlight) return;

    let cancelled = false;

    void (async () => {
      for (const phrase of searchPhrases(highlight.text)) {
        try {
          await search.searchAllPages(phrase).toPromise();
        } catch {
          continue;
        }
        if (cancelled) return;

        const { results } = search.getState();
        if (results.length === 0) continue;

        search.setShowAllResults(true);
        const index = results.findIndex(
          (result) => result.pageIndex === highlight.page - 1,
        );
        if (index >= 0) search.goToResult(index);
        return;
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [highlight]);

  if (!proxiedUrl) {
    return (
      <div className="flex-1 flex items-center justify-center bg-bg-reader">
        <p className="text-body text-text-muted">No PDF available</p>
      </div>
    );
  }

  return (
    <div
      className={cn("flex-1 min-h-0 w-full", className)}
      style={{ height: "100%" }}
    >
      <PDFViewer
        config={{
          src: proxiedUrl,
          theme: {
            preference: "dark",
            dark: {
              accent: { primary: FOLIO_ACCENT, primaryHover: "#34509F" },
            },
          },
          tabBar: "never",
          // Prevent the hamburger from opening/closing other files — Folio
          // controls the single book. Print/export/fullscreen stay available.
          disabledCategories: ["document-open", "document-close"],
        }}
        style={{ width: "100%", height: "100%" }}
        onReady={handleReady}
      />
    </div>
  );
}
