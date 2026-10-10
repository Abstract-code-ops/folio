"use client";

import { useCallback, useEffect, useRef } from "react";
import {
  PDFViewer,
  type PluginRegistry,
  type ScrollCapability,
} from "@embedpdf/react-pdf-viewer";
import { cn } from "@/lib/utils";

export interface PdfViewerProps {
  url: string | null;
  pageNumber: number;
  onPageChange: (page: number) => void;
  className?: string;
}

// Folio's interactive accent, injected into EmbedPDF's dark theme
const FOLIO_ACCENT = "#26418F";

export function PdfViewer({
  url,
  pageNumber,
  onPageChange,
  className,
}: PdfViewerProps) {
  const scrollRef = useRef<ScrollCapability | null>(null);
  const lastReportedPage = useRef<number | null>(null);

  // Proxy the PDF through Next.js so the WASM engine fetches it same-origin
  const proxiedUrl = url ? `/api/pdf?url=${encodeURIComponent(url)}` : null;

  // Wire EmbedPDF's scroll plugin to the parent's page state
  const handleReady = useCallback(
    (registry: PluginRegistry) => {
      const capability = registry
        .getPlugin("scroll")
        ?.provides?.() as ScrollCapability | undefined;
      if (!capability) return;

      scrollRef.current = capability;
      capability.onPageChange(({ pageNumber: p }) => {
        lastReportedPage.current = p;
        onPageChange(p);
      });
    },
    [onPageChange],
  );

  // External jump (coverage map click / skip-to-page): only when the page
  // change did not originate from the viewer's own scrolling
  useEffect(() => {
    if (lastReportedPage.current === pageNumber) return;
    scrollRef.current?.scrollToPage({ pageNumber, behavior: "smooth" });
  }, [pageNumber]);

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
