"use client";

import { Suspense, useEffect, useState, useCallback } from "react";
import { useSearchParams } from "next/navigation";
import { Brain, MessageSquare, FileText } from "lucide-react";
import dynamicImport from "next/dynamic";
import { ChatPanel } from "@/components/chat/ChatPanel";
import { NotesPanel } from "@/components/notes/NotesPanel";
import { Loader } from "@/components/ui/loader";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  ResizablePanelGroup,
  ResizablePanel,
  ResizableHandle,
} from "@/components/ui/resizable";
import { useMediaQuery } from "@/lib/use-media-query";
import { apiClient } from "@/lib/api-client";
import { useChatStore } from "@/lib/chat-store";
import type { BookResponse } from "@/types/books";

const PdfViewer = dynamicImport(
  () => import("@/components/reader/PdfViewer").then((m) => m.PdfViewer),
  { ssr: false },
);

type TabId = "coverage" | "chat" | "notes";
const ALL_TABS: { id: TabId; icon: typeof Brain; label: string }[] = [
  { id: "coverage", icon: Brain, label: "Coverage" },
  { id: "chat", icon: MessageSquare, label: "Chat" },
  { id: "notes", icon: FileText, label: "Notes" },
];

// ── Coverage — coming soon ───────────────────────────────────

function ComingSoon() {
  return (
    <div className="flex h-full flex-col items-center justify-center px-6 text-center">
      <Brain className="h-8 w-8 text-text-subtle mb-3" />
      <p className="text-body font-heading text-text-primary mb-1">Coverage map</p>
      <p className="text-body-sm text-text-muted">Coming soon</p>
    </div>
  );
}

// ── Panel content ─────────────────────────────────────────────

function PanelContent({
  activeTab,
  bookId,
  onNavigateToPage,
}: {
  activeTab: TabId;
  bookId: string;
  onNavigateToPage: (page: number) => void;
}) {
  if (activeTab === "coverage") {
    return <ComingSoon />;
  }
  if (activeTab === "chat") {
    return <ChatPanel bookId={bookId} onNavigateToPage={onNavigateToPage} />;
  }
  return <NotesPanel bookId={bookId} />;
}

// ── Inner component ───────────────────────────────────────────

function ReaderContent() {
  const searchParams = useSearchParams();
  const bookId = searchParams.get("id") ?? "";
  const isDesktop = useMediaQuery("(min-width: 1024px)");

  const [book, setBook] = useState<BookResponse | null>(null);
  const [bookLoading, setBookLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [currentPage, setCurrentPage] = useState(1);
  const [activeTab, setActiveTab] = useState<TabId>("coverage");
  const [mobileSheetOpen, setMobileSheetOpen] = useState(false);

  useEffect(() => {
    if (!bookId) {
      setBookLoading(false);
      setError("No book selected.");
      return;
    }
    let cancelled = false;
    apiClient.getBook(bookId, true)
      .then((data) => { if (!cancelled) setBook(data); })
      .catch((err) => { if (!cancelled) setError(err instanceof Error ? err.message : "Failed to load book"); })
      .finally(() => { if (!cancelled) setBookLoading(false); });

    return () => { cancelled = true; };
  }, [bookId]);

  // Clear this book's chat when leaving the reader (navigate away or switch
  // books), so each book session starts fresh. Tab switches within the reader
  // do not unmount, so the chat persists across them.
  useEffect(() => {
    return () => {
      useChatStore.getState().resetChat(bookId);
    };
  }, [bookId]);

  const handleNavigateToPage = useCallback((page: number) => {
    setCurrentPage(page);
  }, []);

  // ── Error state ─────────────────────────────────────────────
  if (error || !bookId) {
    return (
      <div className="h-screen flex items-center justify-center bg-bg-base">
        <p className="text-body text-state-error mb-2">{error}</p>
        <a href="/library" className="text-body-sm text-accent">← Back to library</a>
      </div>
    );
  }

  // ── Loading state ───────────────────────────────────────────
  if (bookLoading) {
    return (
      <div className="h-screen flex items-center justify-center bg-bg-base">
        <Loader label="Loading book…" />
      </div>
    );
  }

  if (!book) {
    return (
      <div className="h-screen flex items-center justify-center bg-bg-base">
        <p className="text-body text-state-error">Book not found</p>
        <a href="/library" className="text-body-sm text-accent mt-2">← Back to library</a>
      </div>
    );
  }

  // ── Desktop: tabs sit above the panel ───────────────────────
  if (isDesktop) {
    return (
      <div className="h-screen flex flex-col bg-bg-base">
        {/* Top bar — breadcrumb */}
        <div className="flex items-center gap-3 px-4 h-12 border-b border-border-subtle bg-bg-surface shrink-0">
          <a href="/library" className="text-body-sm text-text-muted hover:text-text-primary transition-colors shrink-0">
            ← Library
          </a>
          <span className="text-text-subtle">/</span>
          <span className="font-heading text-body-sm font-semibold text-text-primary truncate">
            {book.title}
          </span>
        </div>

        {/* Left panel (tabs on top) + PDF — resizable */}
        <ResizablePanelGroup
          direction="horizontal"
          className="flex-1 min-h-0"
        >
          {/* Tabs + panel content */}
          <ResizablePanel
            defaultSize={22}
            minSize={15}
            maxSize={50}
            className="bg-bg-surface"
          >
            <div className="flex h-full min-h-0 flex-col">
              <Tabs
                value={activeTab}
                onValueChange={(v) => setActiveTab(v as TabId)}
                className="shrink-0 px-3 py-2 border-b border-border-subtle"
              >
                <TabsList className="w-full bg-bg-elevated border border-border">
                  {ALL_TABS.map(({ id, icon: Icon, label }) => (
                    <TabsTrigger
                      key={id}
                      value={id}
                      className="flex-1 data-[state=active]:bg-bg-surface data-[state=active]:text-text-primary text-text-muted text-body-sm"
                    >
                      <Icon className="h-3.5 w-3.5 mr-1.5" strokeWidth={1.5} />
                      {label}
                    </TabsTrigger>
                  ))}
                </TabsList>
              </Tabs>
              <div className="flex-1 min-h-0 overflow-y-auto">
                <PanelContent
                  activeTab={activeTab}
                  bookId={bookId}
                  onNavigateToPage={handleNavigateToPage}
                />
              </div>
            </div>
          </ResizablePanel>

          <ResizableHandle
            withHandle
            className="bg-border-subtle hover:bg-accent/40 transition-colors data-[resize-handle-state=drag]:bg-accent"
          />

          {/* PDF Viewer */}
          <ResizablePanel defaultSize={78} minSize={50}>
            <main className="flex h-full flex-col bg-bg-reader min-w-0">
              <PdfViewer
                url={book.storage_url}
                pageNumber={currentPage}
                onPageChange={setCurrentPage}
              />
            </main>
          </ResizablePanel>
        </ResizablePanelGroup>
      </div>
    );
  }

  // ── Mobile / Tablet: bottom sheet layout ────────────────────
  return (
    <div className="h-dvh flex flex-col bg-bg-base">
      {/* Top bar */}
      <div className="flex items-center gap-2 px-4 h-10 border-b border-border-subtle bg-bg-surface shrink-0">
        <a href="/library" className="text-body-sm text-text-muted hover:text-text-primary transition-colors shrink-0">
          ← Library
        </a>
        <span className="text-text-subtle">/</span>
        <span className="text-body-sm text-text-muted truncate">{book.title}</span>
        <span className="text-body-sm text-text-subtle ml-auto">p. {currentPage}</span>
      </div>

      {/* PDF Viewer */}
      <main className="flex-1 flex flex-col bg-bg-reader min-h-0">
        <PdfViewer
          url={book.storage_url}
          pageNumber={currentPage}
          onPageChange={setCurrentPage}
        />
      </main>

      {/* Bottom navigation — opens Sheet */}
      <nav
        className="flex items-center justify-around bg-bg-surface border-t border-border-subtle shrink-0"
        style={{
          height: "calc(3.5rem + env(safe-area-inset-bottom))",
          paddingBottom: "env(safe-area-inset-bottom)",
        }}
      >
        {ALL_TABS.map(({ id, icon: Icon, label }) => (
          <Sheet key={id} open={mobileSheetOpen && activeTab === id} onOpenChange={(open) => {
            setMobileSheetOpen(open);
            if (open) setActiveTab(id);
          }}>
            <SheetTrigger asChild>
              <button
                className="flex flex-col items-center gap-0.5 px-4 py-1 rounded-md transition-colors min-h-[44px] min-w-[44px] justify-center text-text-subtle hover:text-text-muted"
              >
                <Icon className="h-4 w-4" strokeWidth={1.5} />
                <span className="text-body-sm">{label}</span>
              </button>
            </SheetTrigger>
            <SheetContent
              side="bottom"
              className="bg-bg-surface border-t border-border-subtle text-text-primary h-[90vh] flex flex-col"
            >
              <SheetHeader className="shrink-0">
                <SheetTitle className="text-text-primary font-heading text-body-sm font-semibold">
                  {label}
                </SheetTitle>
              </SheetHeader>
              <div className="flex-1 min-h-0 overflow-y-auto">
                <PanelContent
                  activeTab={id}
                  bookId={bookId}
                  onNavigateToPage={(page) => {
                    handleNavigateToPage(page);
                    setMobileSheetOpen(false);
                  }}
                />
              </div>
            </SheetContent>
          </Sheet>
        ))}
      </nav>
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
          <Loader />
        </div>
      }
    >
      <ReaderContent />
    </Suspense>
  );
}
