"use client";

import { Suspense, useEffect, useState, useCallback } from "react";
import { useSearchParams } from "next/navigation";
import {
  Loader2,
  Brain,
  MessageSquare,
  FileText,
  Settings,
  X,
} from "lucide-react";
import dynamicImport from "next/dynamic";
import { BrainMap } from "@/components/coverage/BrainMap";
import { ChatPanel } from "@/components/chat/ChatPanel";
import { NotesPanel } from "@/components/notes/NotesPanel";
import { cn } from "@/lib/utils";
import { useMediaQuery } from "@/lib/use-media-query";
import { apiClient } from "@/lib/api-client";
import type { BookResponse } from "@/types/books";
import type { SectionCoverage } from "@/types/coverage";

const PdfViewer = dynamicImport(
  () => import("@/components/reader/PdfViewer").then((m) => m.PdfViewer),
  { ssr: false },
);

// ── Tab config ────────────────────────────────────────────────

type TabId = "coverage" | "chat" | "notes";

const TABS: { id: TabId; icon: typeof Brain; label: string }[] = [
  { id: "coverage", icon: Brain, label: "Coverage" },
  { id: "chat", icon: MessageSquare, label: "Chat" },
  { id: "notes", icon: FileText, label: "Notes" },
];

// ── Coverage skeleton (shown while coverage map loads) ─────────

function CoverageSkeleton() {
  return (
    <div className="p-4 space-y-3">
      <div className="flex items-center justify-between mb-4">
        <div className="h-4 w-20 rounded bg-bg-elevated animate-pulse" />
        <div className="h-3 w-28 rounded bg-bg-elevated animate-pulse" />
      </div>
      <div className="flex items-center gap-3 mb-6">
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="h-3 w-16 rounded bg-bg-elevated animate-pulse" />
        ))}
      </div>
      <div className="flex items-center justify-center py-12">
        <Loader2 className="h-5 w-5 text-text-muted animate-spin" />
      </div>
    </div>
  );
}

// ── Panel content ─────────────────────────────────────────────

function PanelContent({
  activeTab,
  sections,
  bookId,
  onNavigateToPage,
}: {
  activeTab: TabId;
  sections: SectionCoverage[];
  bookId: string;
  onNavigateToPage: (page: number) => void;
}) {
  switch (activeTab) {
    case "coverage":
      return (
        <BrainMap
          sections={sections}
          onChapterClick={(chapter) => {
            // Navigate to the first section's page (approximate)
            const firstSection = sections.find((s) =>
              chapter.sectionIds.includes(s.id),
            );
            if (firstSection) onNavigateToPage(firstSection.page_start);
          }}
        />
      );
    case "chat":
      return (
        <ChatPanel bookId={bookId} onNavigateToPage={onNavigateToPage} />
      );
    case "notes":
      return <NotesPanel bookId={bookId} />;
  }
}

// ── Inner component ───────────────────────────────────────────

function ReaderContent() {
  const searchParams = useSearchParams();
  const bookId = searchParams.get("id") ?? "";

  const [book, setBook] = useState<BookResponse | null>(null);
  const [bookLoading, setBookLoading] = useState(true);
  const [sections, setSections] = useState<SectionCoverage[]>([]);
  const [coverageLoading, setCoverageLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [activeTab, setActiveTab] = useState<TabId>("coverage");
  const [leftPanelOpen, setLeftPanelOpen] = useState(true);
  const [rightPanelOpen, setRightPanelOpen] = useState(false);
  const [currentPage, setCurrentPage] = useState(1);
  const [mobileSurface, setMobileSurface] = useState<TabId | null>(null);

  // Breakpoints
  const isDesktop = useMediaQuery("(min-width: 1280px)");
  const isLaptop = useMediaQuery("(min-width: 1024px) and (max-width: 1279px)");
  const isTablet = useMediaQuery("(min-width: 640px) and (max-width: 1023px)");
  const isMobile = useMediaQuery("(max-width: 639px)");

  useEffect(() => {
    if (!bookId) {
      setBookLoading(false);
      setCoverageLoading(false);
      setError("No book selected. Go back to the library to pick a book.");
      return;
    }

    let cancelled = false;

    apiClient
      .getBook(bookId, true)
      .then((data) => {
        if (!cancelled) setBook(data);
      })
      .catch((err) => {
        if (!cancelled)
          setError(
            err instanceof Error ? err.message : "Failed to load book",
          );
      })
      .finally(() => {
        if (!cancelled) setBookLoading(false);
      });

    apiClient
      .getCoverageMap(bookId)
      .then((data) => {
        if (!cancelled) setSections(data.sections);
      })
      .catch((err) => {
        if (!cancelled)
          setError(
            err instanceof Error ? err.message : "Failed to load coverage",
          );
      })
      .finally(() => {
        if (!cancelled) setCoverageLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [bookId]);

  const handleNavigateToPage = useCallback((page: number) => {
    setCurrentPage(page);
  }, []);

  // ── Mobile actions ──────────────────────────────────────────
  const openMobileSurface = useCallback((tab: TabId) => {
    setMobileSurface(tab);
  }, []);

  const closeMobileSurface = useCallback(() => {
    setMobileSurface(null);
  }, []);

  // ── Tab toggle ──────────────────────────────────────────────
  const handleTabToggle = useCallback(
    (tab: TabId) => {
      if (isMobile || isTablet) {
        openMobileSurface(tab);
      } else if (tab === activeTab) {
        setLeftPanelOpen((p) => !p);
      } else {
        setActiveTab(tab);
        setLeftPanelOpen(true);
      }
    },
    [activeTab, isMobile, isTablet, openMobileSurface],
  );

  // ── Error state ─────────────────────────────────────────────
  if (error || !bookId) {
    return (
      <div className="h-screen flex items-center justify-center bg-bg-base">
        <div className="text-center max-w-sm">
          <p className="text-body text-state-error mb-2">
            {error ?? "No book selected."}
          </p>
          <a
            href="/"
            className="text-body-sm text-accent hover:text-accent-hover transition-colors"
          >
            ← Back to library
          </a>
        </div>
      </div>
    );
  }

  // ── Book loading (book metadata before PDF can show) ────────
  if (bookLoading) {
    return (
      <div className="h-screen flex items-center justify-center bg-bg-base">
        <div className="flex flex-col items-center gap-3">
          <Loader2 className="h-6 w-6 text-text-muted animate-spin" />
          <p className="text-body-sm text-text-muted">Loading book…</p>
        </div>
      </div>
    );
  }

  // ── Book not found after loading ────────────────────────────
  if (!book) {
    return (
      <div className="h-screen flex items-center justify-center bg-bg-base">
        <p className="text-body text-state-error">Book not found</p>
      </div>
    );
  }

  // ── Mobile / Tablet layout ──────────────────────────────────
  if (isMobile || isTablet) {
    const Icon = TABS.find((t) => t.id === activeTab)?.icon ?? Brain;
    return (
      <div className="h-screen flex flex-col bg-bg-base overflow-hidden">
        {/* Reader surface — always visible */}
        <main className="flex-1 flex flex-col bg-bg-reader min-h-0">
          <div className="flex items-center justify-between px-4 h-10 border-b border-border-subtle shrink-0">
            <span className="text-body-sm text-text-muted truncate">
              {book.title} — p. {currentPage}
            </span>
          </div>
          <PdfViewer
            url={book.storage_url}
            pageNumber={currentPage}
            onPageChange={setCurrentPage}
          />
        </main>

        {/* Bottom navigation */}
        <nav className="flex items-center justify-around h-14 bg-bg-surface border-t border-border-subtle shrink-0">
          {TABS.map(({ id, icon: TabIcon, label }) => (
            <button
              key={id}
              onClick={() => handleTabToggle(id)}
              className={cn(
                "flex flex-col items-center gap-0.5 px-4 py-1 rounded-md transition-colors min-h-[44px] min-w-[44px] justify-center",
                activeTab === id && mobileSurface !== id
                  ? "text-accent"
                  : "text-text-subtle hover:text-text-muted",
              )}
            >
              <TabIcon className="h-4 w-4" strokeWidth={1.5} />
              <span className="text-body-sm">{label}</span>
            </button>
          ))}
          <button
            onClick={() => setRightPanelOpen((p) => !p)}
            className="flex flex-col items-center gap-0.5 px-4 py-1 rounded-md text-text-subtle hover:text-text-muted transition-colors min-h-[44px] min-w-[44px] justify-center"
          >
            <Settings className="h-4 w-4" strokeWidth={1.5} />
            <span className="text-body-sm">Info</span>
          </button>
        </nav>

        {/* Mobile bottom sheet — slides up when a tab is active */}
        {mobileSurface && (
          <div className="absolute inset-0 z-50 flex flex-col bg-bg-surface">
            <div className="flex items-center justify-between px-4 py-3 border-b border-border-subtle shrink-0">
              <span className="font-heading text-body-sm font-semibold text-text-primary">
                {TABS.find((t) => t.id === mobileSurface)?.label}
              </span>
              <button
                onClick={closeMobileSurface}
                className="w-8 h-8 flex items-center justify-center rounded-md text-text-subtle hover:text-text-primary hover:bg-bg-elevated transition-colors"
              >
                <X className="h-4 w-4" strokeWidth={1.5} />
              </button>
            </div>
            <div className="flex-1 overflow-y-auto">
              <PanelContent
                activeTab={mobileSurface}
                sections={sections}
                bookId={bookId}
                onNavigateToPage={(page) => {
                  handleNavigateToPage(page);
                  closeMobileSurface();
                }}
              />
            </div>
          </div>
        )}

        {/* Right sidebar for book info on mobile/tablet */}
        {rightPanelOpen && (
          <div className="absolute inset-0 z-50 flex flex-col bg-bg-surface">
            <div className="flex items-center justify-between px-4 py-3 border-b border-border-subtle shrink-0">
              <span className="font-heading text-body-sm font-semibold text-text-primary">
                Book info
              </span>
              <button
                onClick={() => setRightPanelOpen(false)}
                className="w-8 h-8 flex items-center justify-center rounded-md text-text-subtle hover:text-text-primary hover:bg-bg-elevated transition-colors"
              >
                <X className="h-4 w-4" strokeWidth={1.5} />
              </button>
            </div>
            <div className="flex-1 overflow-y-auto p-4">
              <p className="text-body-sm text-text-muted mb-2">
                <span className="text-text-subtle">Title:</span> {book.title}
              </p>
              <p className="text-body-sm text-text-muted mb-2">
                <span className="text-text-subtle">Author:</span> {book.author}
              </p>
              <p className="text-body-sm text-text-muted mb-2">
                <span className="text-text-subtle">Sections:</span>{" "}
                {book.section_count ?? "—"}
              </p>
              <p className="text-body-sm text-text-muted">
                <span className="text-text-subtle">Status:</span>{" "}
                {book.ingestion_status}
              </p>
            </div>
          </div>
        )}
      </div>
    );
  }

  // ── Desktop / Laptop layout ─────────────────────────────────
  return (
    <div className="h-screen flex bg-bg-base overflow-hidden">
      {/* Icon rail */}
      <nav className="w-rail flex flex-col items-center py-3 gap-2 bg-bg-surface border-r border-border-subtle shrink-0">
        <div className="mb-4 mt-1">
          <div className="w-7 h-7 rounded-lg bg-accent flex items-center justify-center">
            <span className="text-white font-heading text-body-sm font-bold">
              F
            </span>
          </div>
        </div>
        {TABS.map(({ id, icon: TabIcon, label }) => (
          <button
            key={id}
            onClick={() => handleTabToggle(id)}
            title={label}
            className={cn(
              "w-9 h-9 rounded-lg flex items-center justify-center transition-colors",
              activeTab === id && (leftPanelOpen || isLaptop)
                ? "bg-accent/15 text-accent"
                : "text-text-subtle hover:text-text-muted hover:bg-bg-elevated",
            )}
          >
            <TabIcon className="h-4 w-4" strokeWidth={1.5} />
          </button>
        ))}
        <div className="flex-1" />
        <button
          onClick={() => setRightPanelOpen((p) => !p)}
          title="Settings"
          className="w-9 h-9 rounded-lg flex items-center justify-center text-text-subtle hover:text-text-muted hover:bg-bg-elevated transition-colors"
        >
          <Settings className="h-4 w-4" strokeWidth={1.5} />
        </button>
      </nav>

      {/* Left panel — coverage skeleton while loading, content when ready */}
      {leftPanelOpen && isLaptop && (
        <div
          className="absolute inset-0 z-40 flex"
          style={{ left: "48px" }}
        >
          <div
            className="flex-1 bg-black/40"
            onClick={() => setLeftPanelOpen(false)}
          />
          <aside className="w-panel bg-bg-surface border-r border-border-subtle overflow-y-auto shrink-0">
            {coverageLoading ? (
              <CoverageSkeleton />
            ) : (
              <PanelContent
                activeTab={activeTab}
                sections={sections}
                bookId={bookId}
                onNavigateToPage={handleNavigateToPage}
              />
            )}
          </aside>
        </div>
      )}

      {/* Left panel — on desktop it's side-by-side */}
      {isDesktop && (
        <aside
          className={cn(
            "panel-slide bg-bg-surface border-r border-border-subtle overflow-hidden shrink-0",
            leftPanelOpen ? "w-panel opacity-100" : "w-0 opacity-0",
          )}
        >
          {leftPanelOpen && (
            <div className="w-panel h-full overflow-y-auto">
              {coverageLoading ? (
                <CoverageSkeleton />
              ) : (
                <PanelContent
                  activeTab={activeTab}
                  sections={sections}
                  bookId={bookId}
                  onNavigateToPage={handleNavigateToPage}
                />
              )}
            </div>
          )}
        </aside>
      )}

      {/* PDF Reader */}
      <main
        className={cn(
          "flex-1 bg-bg-reader flex flex-col",
          isDesktop ? "min-w-[600px]" : "min-w-0",
        )}
      >
        <div className="flex items-center justify-between px-4 h-10 border-b border-border-subtle shrink-0">
          <span className="text-body-sm text-text-muted truncate">
            {book.title} — p. {currentPage}
          </span>
          <span className="text-body-sm text-text-subtle shrink-0">
            {sections.length} sections
          </span>
        </div>
        <PdfViewer
          url={book.storage_url}
          pageNumber={currentPage}
          onPageChange={setCurrentPage}
        />
      </main>

      {/* Right sidebar — desktop only */}
      {isDesktop && (
        <aside
          className={cn(
            "panel-slide bg-bg-surface border-l border-border-subtle overflow-hidden shrink-0",
            rightPanelOpen ? "w-panel-right opacity-100" : "w-0 opacity-0",
          )}
        >
          {rightPanelOpen && (
            <div className="w-panel-right h-full overflow-y-auto p-4">
              <h3 className="font-heading text-body-sm font-semibold text-text-primary mb-4">
                Book info
              </h3>
              <p className="text-body-sm text-text-muted mb-2">
                <span className="text-text-subtle">Title:</span> {book.title}
              </p>
              <p className="text-body-sm text-text-muted mb-2">
                <span className="text-text-subtle">Author:</span> {book.author}
              </p>
              <p className="text-body-sm text-text-muted mb-2">
                <span className="text-text-subtle">Sections:</span>{" "}
                {book.section_count ?? "—"}
              </p>
              <p className="text-body-sm text-text-muted">
                <span className="text-text-subtle">Status:</span>{" "}
                {book.ingestion_status}
              </p>
            </div>
          )}
        </aside>
      )}
    </div>
  );
}

// ── Exported page ─────────────────────────────────────────────

export const dynamic = "force-dynamic";

export default function ReaderPage() {
  return (
    <Suspense
      fallback={
        <div className="h-screen flex items-center justify-center bg-bg-base">
          <Loader2 className="h-6 w-6 text-text-muted animate-spin" />
        </div>
      }
    >
      <ReaderContent />
    </Suspense>
  );
}
