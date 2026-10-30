"use client";

import { Suspense, useEffect, useMemo, useRef, useState, useCallback } from "react";import { useSearchParams } from "next/navigation";
import { Brain, Contrast, MessageSquare, FileText, PanelLeftClose, PanelLeftOpen } from "lucide-react";
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
import type { ImperativePanelHandle } from "react-resizable-panels";
import { useMediaQuery } from "@/lib/use-media-query";
import { apiClient } from "@/lib/api-client";
import { useChatStore } from "@/lib/chat-store";
import { useCiteBridge } from "@/lib/cite-bridge";
import { makeLocalNote, useNotesNav, useNotesStore, type LocalLink } from "@/lib/notes-store";
import { syncUserData } from "@/lib/sync";
import { startNoteSync } from "@/lib/note-sync";
import type { BookResponse } from "@/types/books";
import type { HighlightTarget, PdfSelection } from "@/components/reader/PdfViewer";

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
  sectionId,
  sectionHeading,
  suggestions,
  onCitationClick,
}: {
  activeTab: TabId;
  bookId: string;
  sectionId?: string;
  sectionHeading?: string;
  suggestions?: string[];
  onCitationClick: (target: { page: number; text: string }) => void;
}) {
  if (activeTab === "coverage") {
    return <ComingSoon />;
  }
  if (activeTab === "chat") {
    return (
      <ChatPanel
        bookId={bookId}
        suggestions={suggestions}
        onCitationClick={onCitationClick}
      />
    );
  }
  return (
    <NotesPanel
      bookId={bookId}
      sectionId={sectionId}
      sectionHeading={sectionHeading}
      onCitationClick={onCitationClick}
    />
  );
}

// ── PDF selection menu ─────────────────────────────────────────

function SelectionMenuBar({
  selection,
  notes,
  onAskChat,
  onNewNote,
  onExistingNote,
  onClose,
}: {
  selection: PdfSelection;
  notes: { id: string; title: string | null }[];
  onAskChat: (sel: PdfSelection) => void;
  onNewNote: (sel: PdfSelection) => void;
  onExistingNote: (noteId: string, sel: PdfSelection) => void;
  onClose: () => void;
}) {
  const [addOpen, setAddOpen] = useState(false);
  const [picking, setPicking] = useState(false);

  const action = "min-h-11 rounded-md px-3 py-1.5 text-body-sm transition-colors sm:min-h-0";

  return (
    <div
      onClick={(event) => event.stopPropagation()}
      className="absolute inset-x-0 bottom-0 z-20 flex flex-col items-center gap-2 p-3"
    >
      <div className="flex items-center gap-1 rounded-lg border border-border bg-bg-surface p-1 shadow-xl">
        {!addOpen && !picking && (
          <>
            <button
              onClick={() => onAskChat(selection)}
              className={`${action} bg-accent text-white hover:bg-accent-hover`}
            >
              Ask chat
            </button>
            <button
              onClick={() => setAddOpen(true)}
              className={`${action} text-text-primary hover:bg-bg-elevated`}
            >
              Add to note
            </button>
          </>
        )}

        {addOpen && !picking && (
          <>
            <button
              onClick={() => onNewNote(selection)}
              className={`${action} bg-accent text-white hover:bg-accent-hover`}
            >
              New note
            </button>
            <button
              onClick={() => setPicking(true)}
              className={`${action} text-text-primary hover:bg-bg-elevated`}
            >
              Existing note
            </button>
          </>
        )}

        <button
          onClick={onClose}
          aria-label="Dismiss"
          className="min-h-11 min-w-11 rounded-md px-2 text-text-subtle hover:bg-bg-elevated hover:text-text-primary sm:min-h-0"
        >
          ×
        </button>
      </div>

      {picking && (
        <div className="max-h-48 w-full max-w-sm overflow-y-auto rounded-lg border border-border bg-bg-surface p-1 shadow-xl">
          {notes.length === 0 ? (
            <p className="px-3 py-2 text-body-sm text-text-muted">No notes yet.</p>
          ) : (
            notes.map((note) => (
              <button
                key={note.id}
                onClick={() => onExistingNote(note.id, selection)}
                className="block w-full truncate rounded px-3 py-2 text-left text-body-sm text-text-primary hover:bg-bg-elevated"
              >
                {note.title ?? "Untitled note"}
              </button>
            ))
          )}
        </div>
      )}
    </div>
  );
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
  // Chrome hides on a tap in the page area and returns on the next one: the
  // reading surface is the point, the bars are furniture.
  const [chromeHidden, setChromeHidden] = useState(false);
  // Dim rather than invert: inverting a PDF wrecks its figures and images.
  const [dim, setDim] = useState(false);
  // Desktop panel collapse. The reader is the point, so the panel can get out of
  // the way entirely. The panel is a resizable pane, so it keeps its width when
  // open; the toggle drives its imperative handle rather than tearing down the
  // whole group, and the trigger carries aria-controls for that region.
  const [panelCollapsed, setPanelCollapsed] = useState(false);
  const panelRef = useRef<ImperativePanelHandle>(null);
  const togglePanel = useCallback(() => {
    if (panelCollapsed) panelRef.current?.expand();
    else panelRef.current?.collapse();
  }, [panelCollapsed]);
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

  // Cache-miss sync: on first open of a book, pull the current user's notes and
  // chat history from the server; afterwards local is the cache. Auth-scoped
  // server-side, so this is "the user's data", not everyone's.
  useEffect(() => {
    if (!bookId) return;
    startNoteSync();
    void syncUserData(bookId);
  }, [bookId]);

  // Open where reading begins. Page 1 is the cover and copyright page in most
  // books, which is chrome, not reading; the first chapter-level section is where
  // a student actually starts. Runs once per book, so a page the student chose is
  // never overridden.
  const openedAtStart = useRef(false);  useEffect(() => {
    if (openedAtStart.current || !book?.sections?.length) return;
    openedAtStart.current = true;
    const firstChapter = book.sections.find((section) => section.level >= 1);
    if (firstChapter) setCurrentPage(firstChapter.page_start);
  }, [book]);

  // A citation click both jumps to its page and asks the viewer to highlight
  // the cited text. Highlight lives in state so re-clicking the same citation
  // still re-runs the search.
  const [highlight, setHighlight] = useState<HighlightTarget | null>(null);
  const handleCitationClick = useCallback(
    ({ page, text }: { page: number; text: string }) => {
      setCurrentPage(page);
      setHighlight({ page, text });
    },
    [],
  );

  // PDF text selection drives two things: a cite in flight (resolved here into a
  // link) and, otherwise, the "Ask chat / Add to note" menu.
  const [pdfSelection, setPdfSelection] = useState<PdfSelection | null>(null);
  const notes = useNotesStore((s) => s.notes);
  const bookNotes = useMemo(
    () =>
      Object.values(notes)
        .filter((note) => note.bookId === bookId)
        .map((note) => ({ id: note.id, title: note.title })),
    [notes, bookId],
  );

  const sectionAtPage = useCallback(
    (page: number) => {
      const sections = book?.sections;
      if (!sections || sections.length === 0) return null;
      const containing = sections.filter(
        (section) => page >= section.page_start && page <= section.page_end,
      );
      if (containing.length === 0) return null;
      return containing.sort(
        (a, b) =>
          a.page_end - a.page_start - (b.page_end - b.page_start) ||
          b.level - a.level,
      )[0];
    },
    [book],
  );

  const linkFor = useCallback(
    (sel: PdfSelection, quote?: string | null): LocalLink => {
      const section = sectionAtPage(sel.page);
      return {
        id: crypto.randomUUID(),
        section_id: section?.id ?? null,
        anchor_heading_path: section?.heading ?? `p. ${sel.page}`,
        page_start: sel.page,
        page_end: sel.page,
        excerpt: sel.text,
        quote: quote ?? undefined,
        status: "accepted",
        origin: "manual",
      };
    },
    [sectionAtPage],
  );

  const onSelection = useCallback(
    (sel: PdfSelection | null) => {
      if (!sel) {
        setPdfSelection(null);
        return;
      }
      const request = useCiteBridge.getState().citeRequest;
      if (request) {
        useCiteBridge.getState().setResolvedLink({
          noteId: request.noteId,
          blockId: request.blockId,
          link: linkFor(sel, request.quote),
        });
        useCiteBridge.getState().setCiteRequest(null);
        return;
      }
      setPdfSelection(sel);
    },
    [linkFor],
  );

  const askChat = useCallback(
    (sel: PdfSelection) => {
      const store = useChatStore.getState();
      store.createSession(bookId);
      store.setPendingSeed(
        bookId,
        `Explain this passage and what it means in this book:\n\n"${sel.text}"`,
      );
      setActiveTab("chat");
      setPdfSelection(null);
    },
    [bookId],
  );

  const addToNewNote = useCallback(
    (sel: PdfSelection) => {
      const note = makeLocalNote(bookId, {
        blocks: [
          {
            id: crypto.randomUUID(),
            kind: "paragraph",
            text: sel.text,
            origin: "typed",
            links: [linkFor(sel)],
          },
        ],
      });
      useNotesStore.getState().saveNote(note);
      useNotesNav.getState().open(bookId, note.id);
      useNotesNav.getState().setEditing(bookId, true);
      setActiveTab("notes");
      setPdfSelection(null);
    },
    [bookId, linkFor],
  );

  const addToExistingNote = useCallback(
    (noteId: string, sel: PdfSelection) => {
      useNotesStore.getState().appendBlock(noteId, {
        id: crypto.randomUUID(),
        kind: "paragraph",
        text: sel.text,
        origin: "typed",
        links: [linkFor(sel)],
      });
      useNotesNav.getState().open(bookId, noteId);
      setActiveTab("notes");
      setPdfSelection(null);
    },
    [bookId, linkFor],
  );

  // Which section the current page is in, resolved from the section map that
  // arrives with the book. Resolved locally on purpose: asking the coverage map
  // costs seconds and carries every section's score just to answer this.
  const currentSection = useMemo(() => {
    const sections = book?.sections;
    if (!sections || sections.length === 0) return null;
    const containing = sections.filter(
      (section) =>
        currentPage >= section.page_start && currentPage <= section.page_end,
    );
    if (containing.length === 0) return null;
    // A chapter's range contains its subsections': prefer the tightest.
    return containing.sort(
      (a, b) =>
        a.page_end - a.page_start - (b.page_end - b.page_start) ||
        b.level - a.level,
    )[0];
  }, [book, currentPage]);

  // Example questions for the chat empty state, built from the book's own
  // chapter headings so they are answerable from this book by construction.
  const chatSuggestions = useMemo(
    () =>
      (book?.sections ?? [])
        .filter((section) => section.level >= 1)
        .slice(0, 3)
        .map((section) => `What is "${section.heading}" about?`),
    [book],
  );
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
          <button
            type="button"
            onClick={togglePanel}
            aria-expanded={!panelCollapsed}
            aria-controls="study-panel"
            aria-label={panelCollapsed ? "Show study panel" : "Hide study panel"}
            className="inline-flex min-h-11 min-w-11 items-center justify-center rounded text-text-muted transition-colors hover:text-text-primary shrink-0"
          >
            {panelCollapsed ? (
              <PanelLeftOpen className="h-4 w-4" strokeWidth={1.5} />
            ) : (
              <PanelLeftClose className="h-4 w-4" strokeWidth={1.5} />
            )}
          </button>
          <a href="/library" className="inline-flex min-h-11 items-center text-body-sm text-text-muted hover:text-text-primary transition-colors shrink-0">
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
          {/* Tabs + panel content. Collapsible to zero so the reader takes the
              freed width; the top-bar trigger drives it via aria-controls. */}
          <ResizablePanel
            ref={panelRef}
            defaultSize={22}
            minSize={15}
            maxSize={50}
            collapsible
            collapsedSize={0}
            onCollapse={() => setPanelCollapsed(true)}
            onExpand={() => setPanelCollapsed(false)}
            className="bg-bg-surface"
          >
            <div id="study-panel" className="flex h-full min-h-0 flex-col">
              {!panelCollapsed && (
                <>
                  <Tabs
                    value={activeTab}
                    onValueChange={(v) => setActiveTab(v as TabId)}
                    className="shrink-0 px-3 py-2 border-b border-border-subtle"
                  >
                    <TabsList className="w-full bg-bg-elevated border border-border p-1">
                      {ALL_TABS.map(({ id, icon: Icon, label }) => (
                        <TabsTrigger
                          key={id}
                          value={id}
                          className="flex-1 min-h-11 px-3 py-2 data-[state=active]:bg-bg-surface data-[state=active]:text-text-primary text-text-muted text-body-sm"
                        >
                          <Icon className="h-3.5 w-3.5 mr-1.5" strokeWidth={1.5} />
                          {label}
                        </TabsTrigger>
                      ))}
                    </TabsList>
                  </Tabs>
                  <div className="flex flex-1 min-h-0 flex-col overflow-hidden">
                    <PanelContent
                      activeTab={activeTab}
                      bookId={bookId}
                      sectionId={currentSection?.id}
                      sectionHeading={currentSection?.heading}
                      suggestions={chatSuggestions}
                      onCitationClick={handleCitationClick}
                    />
                  </div>
                </>
              )}
            </div>
          </ResizablePanel>

          <ResizableHandle
            withHandle
            className="bg-border-subtle hover:bg-accent/40 transition-colors data-[resize-handle-state=drag]:bg-accent"
          />

          {/* PDF Viewer */}
          <ResizablePanel defaultSize={78} minSize={50}>
            <main className="relative flex h-full flex-col bg-bg-reader min-w-0">
              <PdfViewer
                url={book.storage_url}
                pageNumber={currentPage}
                onPageChange={setCurrentPage}
                highlight={highlight}
                onSelection={onSelection}
              />
              {pdfSelection && (
                <SelectionMenuBar
                  selection={pdfSelection}
                  notes={bookNotes}
                  onAskChat={askChat}
                  onNewNote={addToNewNote}
                  onExistingNote={addToExistingNote}
                  onClose={() => setPdfSelection(null)}
                />
              )}
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
      <div
        className={`flex items-center gap-2 px-4 h-10 border-b border-border-subtle bg-bg-surface shrink-0 transition-opacity motion-reduce:transition-none ${chromeHidden ? "pointer-events-none opacity-0" : "opacity-100"}`}
      >
        <a href="/library" className="inline-flex min-h-11 items-center text-body-sm text-text-muted hover:text-text-primary transition-colors shrink-0">
          ← Library
        </a>
        <span className="text-text-subtle">/</span>
        <h1 className="sr-only">{book.title}</h1>
        <span className="text-body-sm text-text-muted truncate">{book.title}</span>
        <button
          onClick={() => setDim((value) => !value)}
          aria-pressed={dim}
          aria-label="Dim the page"
          className="inline-flex min-h-11 min-w-11 items-center justify-center rounded text-text-subtle transition-colors hover:text-text-primary"
        >
          <Contrast className="h-4 w-4" strokeWidth={1.5} />
        </button>
        <span
          role="status"
          aria-live="polite"
          className="text-body-sm text-text-subtle ml-auto"
        >
          p. {currentPage}
        </span>
      </div>

      {/* PDF Viewer */}
      <main
        onClick={() => setChromeHidden((hidden) => !hidden)}
        className={`relative flex-1 flex flex-col bg-bg-reader min-h-0 transition-[filter] motion-reduce:transition-none ${dim ? "brightness-[0.85]" : ""}`}
      >
        <PdfViewer
          url={book.storage_url}
          pageNumber={currentPage}
          onPageChange={setCurrentPage}
          highlight={highlight}
          onSelection={onSelection}
        />
        {pdfSelection && (
          <SelectionMenuBar
            selection={pdfSelection}
            notes={bookNotes}
            onAskChat={askChat}
            onNewNote={addToNewNote}
            onExistingNote={addToExistingNote}
            onClose={() => setPdfSelection(null)}
          />
        )}
      </main>

      {/* Bottom navigation — opens Sheet */}
      <nav
        className={`flex items-center justify-around bg-bg-surface border-t border-border-subtle shrink-0 transition-opacity motion-reduce:transition-none ${chromeHidden ? "pointer-events-none opacity-0" : "opacity-100"}`}
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
              className="bg-bg-surface border-t border-border-subtle text-text-primary h-[90vh] flex flex-col min-h-0"
            >
              <SheetHeader className="shrink-0">
                <SheetTitle className="text-text-primary font-heading text-body-sm font-semibold">
                  {label}
                </SheetTitle>
              </SheetHeader>
              <div className="flex flex-1 min-h-0 flex-col overflow-hidden">
                <PanelContent
                  activeTab={id}
                  bookId={bookId}
                  sectionId={currentSection?.id}
                  sectionHeading={currentSection?.heading}
                  suggestions={chatSuggestions}
                  onCitationClick={(target) => {
                    handleCitationClick(target);
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
