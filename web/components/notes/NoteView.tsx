"use client";

import { useState, type ReactNode } from "react";
import {
  AlertCircle,
  ArrowLeft,
  FileText,
  Pencil,
  Trash2,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useNotesStore, type LocalBlock, type LocalLink } from "@/lib/notes-store";

export interface NoteViewProps {
  noteId: string;
  /** Return to the note list. */
  onBack: () => void;
  /** Open the editor. Hidden when the caller is read-only. */
  onEdit?: () => void;
  /** Jump the reader to a cited page and highlight the excerpt. */
  onCitationClick?: (target: { page: number; text: string }) => void;
  className?: string;
}

/**
 * A note's citation number, assigned at render time.
 *
 * Numbers are not stored: the same section is `[1]` in every note that cites it
 * first, and inserting a paragraph earlier renumbers the note without a write.
 */
function buildSourceNumbers(blocks: LocalBlock[]): Map<string, number> {
  const numbers = new Map<string, number>();
  for (const block of blocks) {
    for (const link of block.links) {
      if (link.status === "dismissed") continue;
      const key = link.section_id ?? link.anchor_heading_path;
      if (!numbers.has(key)) numbers.set(key, numbers.size + 1);
    }
  }
  return numbers;
}

function pagesLabel(link: LocalLink): string {
  return link.page_end !== link.page_start
    ? `pp. ${link.page_start}–${link.page_end}`
    : `p. ${link.page_start}`;
}

// ── Cited-text highlighting ────────────────────────────────────
// A citation is underlined and link-coloured so it reads as "this phrase came
// from the book", distinct from the card's left bar (which is the card's own
// identity). Links carry the exact note phrase in `quote`; a link without a
// quote cites the whole block.

function citedQuotes(block: LocalBlock): string[] {
  return block.links
    .filter((link) => link.status !== "dismissed" && link.quote)
    .map((link) => link.quote as string);
}

function wholeBlockCited(block: LocalBlock): boolean {
  return block.links.some((link) => link.status !== "dismissed" && !link.quote);
}

const CITED = "text-accent underline decoration-accent/60 underline-offset-2";

function CitedText({ text, quotes }: { text: string; quotes: string[] }) {
  if (quotes.length === 0) return <>{text}</>;

  const marks = quotes
    .map((quote) => ({ quote, index: text.indexOf(quote) }))
    .filter((mark) => mark.index >= 0)
    .sort((a, b) => a.index - b.index);

  if (marks.length === 0) return <>{text}</>;

  const parts: ReactNode[] = [];
  let last = 0;
  for (const mark of marks) {
    if (mark.index > last) parts.push(text.slice(last, mark.index));
    parts.push(
      <span key={mark.index} className={CITED}>
        {text.slice(mark.index, mark.index + mark.quote.length)}
      </span>,
    );
    last = mark.index + mark.quote.length;
  }
  if (last < text.length) parts.push(text.slice(last));
  return <>{parts}</>;
}

function citedNode(text: string, quotes: string[], wholeCited: boolean): ReactNode {
  return wholeCited ? text : <CitedText text={text} quotes={quotes} />;
}

function CitationChip({
  link,
  number,
  onCitationClick,
  onRemove,
}: {
  link: LocalLink;
  number: number;
  onCitationClick?: (target: { page: number; text: string }) => void;
  onRemove?: () => void;
}) {
  // A link whose section was deleted keeps its stored pages but cannot jump.
  if (link.section_id === null) {
    return (
      <span className="inline-flex items-center rounded border border-dashed border-border px-1.5 py-1 text-body-sm text-text-muted">
        [{number}] source moved
      </span>
    );
  }

  return (
    <span className="group/chip relative inline-flex">
      <button
        type="button"
        aria-label={`Source ${number}: ${link.anchor_heading_path}, ${pagesLabel(link)}`}
        onClick={() =>
          onCitationClick?.({ page: link.page_start, text: link.excerpt })
        }
        className="inline-flex min-h-11 items-center gap-1 rounded px-1.5 text-body-sm text-accent transition-colors hover:bg-accent/10 sm:min-h-0"
      >
        <span aria-hidden>[{number}]</span>
        <span className="text-text-subtle">{pagesLabel(link)}</span>
      </button>

      <span
        role="tooltip"
        className="pointer-events-none absolute bottom-full left-0 z-30 w-64 rounded-md border border-border bg-bg-elevated p-2.5 text-left opacity-0 shadow-xl transition-opacity group-hover/chip:pointer-events-auto group-hover/chip:opacity-100 group-focus-within/chip:pointer-events-auto group-focus-within/chip:opacity-100"
      >
        <span className="block text-body-sm text-text-primary">
          {link.anchor_heading_path}
        </span>
        <span className="mt-0.5 block text-body-sm text-text-subtle">
          {pagesLabel(link)}
        </span>
        <span className="mt-1.5 block text-body-sm text-text-muted">
          {link.excerpt}
        </span>
        <span className="mt-2 flex items-center justify-between gap-2">
          <span className="text-body-sm text-accent">Open in reader →</span>
          {onRemove && (
            <button
              type="button"
              onClick={onRemove}
              className="rounded px-1.5 py-0.5 text-body-sm text-state-error transition-colors hover:bg-state-error/10"
            >
              Remove
            </button>
          )}
        </span>
      </span>
    </span>
  );
}

function Chips({
  links,
  sourceNumbers,
  onCitationClick,
  onRemoveLink,
}: {
  links: LocalLink[];
  sourceNumbers: Map<string, number>;
  onCitationClick?: (target: { page: number; text: string }) => void;
  onRemoveLink?: (linkId: string) => void;
}) {
  const visible = links.filter((link) => link.status !== "dismissed");
  if (visible.length === 0) return null;

  return (
    <span className="mt-1 flex flex-wrap gap-1">
      {visible.map((link) => (
        <CitationChip
          key={link.id}
          link={link}
          number={
            sourceNumbers.get(link.section_id ?? link.anchor_heading_path) ?? 1
          }
          onCitationClick={onCitationClick}
          onRemove={onRemoveLink ? () => onRemoveLink(link.id) : undefined}
        />
      ))}
    </span>
  );
}

function CardBody({
  block,
  sourceNumbers,
  onCitationClick,
  onRemoveLink,
  quotes,
  wholeCited,
}: {
  block: LocalBlock;
  sourceNumbers: Map<string, number>;
  onCitationClick?: (target: { page: number; text: string }) => void;
  onRemoveLink?: (linkId: string) => void;
  quotes: string[];
  wholeCited: boolean;
}) {
  const parts = block.text
    .split(/\n{2,}/)
    .map((part) => part.trim())
    .filter(Boolean);

  const [concept, ...rest] = parts;
  const exampleIndex = rest.findIndex((part) => /^example:/i.test(part));

  return (
    <div className="note-card rounded-md border border-border-subtle border-l-2 border-l-accent/60 bg-bg-base py-3.5 pl-3 pr-3.5">
      <p className={cn("text-body-lg font-medium text-text-primary", wholeCited && CITED)}>
        {citedNode(concept, quotes, wholeCited)}
      </p>

      {rest.map((part, index) => {
        const isExample = index === exampleIndex;
        const text = isExample ? part.replace(/^example:\s*/i, "") : part;
        return (
          <p
            key={index}
            className={cn(
              "mt-2 text-body-lg",
              wholeCited
                ? CITED
                : isExample
                  ? "text-text-muted"
                  : "text-text-primary",
            )}
          >
            {isExample && !wholeCited && (
              <span className="mr-1.5 text-body-sm text-text-subtle">
                Example
              </span>
            )}
            {citedNode(text, quotes, wholeCited)}
          </p>
        );
      })}

      <Chips
        links={block.links}
        sourceNumbers={sourceNumbers}
        onCitationClick={onCitationClick}
        onRemoveLink={onRemoveLink}
      />
    </div>
  );
}

function BlockView({
  block,
  sourceNumbers,
  onCitationClick,
  onRemoveLink,
}: {
  block: LocalBlock;
  sourceNumbers: Map<string, number>;
  onCitationClick?: (target: { page: number; text: string }) => void;
  onRemoveLink?: (linkId: string) => void;
}) {
  const quotes = citedQuotes(block);
  const wholeCited = wholeBlockCited(block);

  if (block.kind === "card") {
    return (
      <CardBody
        block={block}
        sourceNumbers={sourceNumbers}
        onCitationClick={onCitationClick}
        onRemoveLink={onRemoveLink}
        quotes={quotes}
        wholeCited={wholeCited}
      />
    );
  }

  if (block.kind === "heading") {
    return (
      <p className="mt-4 text-body-lg font-semibold text-text-primary first:mt-0">
        {block.text}
      </p>
    );
  }

  if (block.kind === "bullet") {
    return (
      <div className="flex gap-2">
        <span className="shrink-0 text-text-subtle">•</span>
        <div className="min-w-0">
          <p className={cn("whitespace-pre-wrap text-body-lg text-text-primary", wholeCited && CITED)}>
            {citedNode(block.text, quotes, wholeCited)}
          </p>
          <Chips
            links={block.links}
            sourceNumbers={sourceNumbers}
            onCitationClick={onCitationClick}
            onRemoveLink={onRemoveLink}
          />
        </div>
      </div>
    );
  }

  return (
    <div>
      <p className={cn("whitespace-pre-wrap text-body-lg text-text-primary", wholeCited && CITED)}>
        {citedNode(block.text, quotes, wholeCited)}
      </p>
      <Chips
        links={block.links}
        sourceNumbers={sourceNumbers}
        onCitationClick={onCitationClick}
        onRemoveLink={onRemoveLink}
      />
    </div>
  );
}

export function NoteView({
  noteId,
  onBack,
  onEdit,
  onCitationClick,
  className,
}: NoteViewProps) {
  const note = useNotesStore((s) => s.notes[noteId]);
  const renameNote = useNotesStore((s) => s.renameNote);
  const deleteNote = useNotesStore((s) => s.deleteNote);
  const removeLink = useNotesStore((s) => s.removeLink);

  const [renaming, setRenaming] = useState(false);
  const [draftTitle, setDraftTitle] = useState("");
  const [confirmDelete, setConfirmDelete] = useState(false);

  const sourceNumbers = buildSourceNumbers(note?.blocks ?? []);

  const commitRename = () => {
    renameNote(noteId, draftTitle.trim() || null);
    setRenaming(false);
  };

  const handleDelete = () => {
    if (!confirmDelete) {
      setConfirmDelete(true);
      // A stray tap must not wipe a note — reset after a moment.
      setTimeout(() => setConfirmDelete(false), 3000);
      return;
    }
    deleteNote(noteId);
    onBack();
  };

  const handleRemoveLink = (blockId: string, linkId: string) => {
    removeLink(noteId, blockId, linkId);
  };

  if (!note) {
    return (
      <div className={cn("flex min-h-0 flex-1 flex-col", className)}>
        <div className="shrink-0 border-b border-border-subtle px-5 py-4 lg:px-6">
          <button
            onClick={onBack}
            className="inline-flex min-h-11 items-center gap-1.5 text-body-sm text-text-muted transition-colors hover:text-text-primary sm:min-h-0"
          >
            <ArrowLeft className="h-3.5 w-3.5" strokeWidth={1.5} />
            All notes
          </button>
        </div>
        <div className="flex flex-1 flex-col items-center justify-center px-4 py-12 text-center">
          <AlertCircle className="mb-3 h-8 w-8 text-text-subtle" />
          <p className="text-body text-text-muted">This note no longer exists.</p>
        </div>
      </div>
    );
  }

  return (
    <div className={cn("flex min-h-0 flex-1 flex-col", className)}>
      <div className="shrink-0 border-b border-border-subtle px-5 py-4 lg:px-6">
        <div className="flex items-center justify-between gap-3">
          <button
            onClick={onBack}
            className="inline-flex min-h-11 items-center gap-1.5 text-body-sm text-text-muted transition-colors hover:text-text-primary sm:min-h-0"
          >
            <ArrowLeft className="h-3.5 w-3.5" strokeWidth={1.5} />
            All notes
          </button>
          {onEdit && (
            <button
              onClick={onEdit}
              className="rounded px-2 py-1 text-body-sm text-text-muted transition-colors hover:bg-bg-elevated hover:text-text-primary"
            >
              Edit
            </button>
          )}
        </div>

        <div className="mt-2 flex items-center gap-2">
          {renaming ? (
            <input
              autoFocus
              value={draftTitle}
              onChange={(event) => setDraftTitle(event.target.value)}
              onBlur={commitRename}
              onKeyDown={(event) => {
                if (event.key === "Enter") commitRename();
                if (event.key === "Escape") setRenaming(false);
              }}
              className="w-full rounded-md border border-border bg-bg-base px-2 py-1 text-body font-heading font-semibold text-text-primary outline-none focus:border-accent/50"
            />
          ) : (
            <h2 className="min-w-0 flex-1 truncate font-heading text-body font-semibold text-text-primary">
              {note.title ?? "Untitled note"}
            </h2>
          )}

          {!renaming && (
            <>
              <button
                onClick={() => {
                  setDraftTitle(note.title ?? "");
                  setRenaming(true);
                }}
                aria-label="Rename note"
                className="inline-flex min-h-11 min-w-11 items-center justify-center rounded text-text-subtle transition-colors hover:bg-bg-elevated hover:text-text-primary sm:min-h-0 sm:min-w-0"
              >
                <Pencil className="h-3.5 w-3.5" strokeWidth={1.5} />
              </button>
              <button
                onClick={handleDelete}
                aria-label={confirmDelete ? "Confirm delete" : "Delete note"}
                className={cn(
                  "inline-flex min-h-11 min-w-11 items-center justify-center rounded px-2 transition-colors sm:min-h-0 sm:min-w-0",
                  confirmDelete
                    ? "text-state-error hover:bg-state-error/10"
                    : "text-text-subtle hover:bg-bg-elevated hover:text-text-primary",
                )}
              >
                {confirmDelete ? (
                  <span className="text-body-sm">Confirm</span>
                ) : (
                  <Trash2 className="h-3.5 w-3.5" strokeWidth={1.5} />
                )}
              </button>
            </>
          )}
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-5 py-4 lg:px-6">
        {note.blocks.length === 0 ? (
          <div className="flex flex-col items-center justify-center px-4 py-12 text-center">
            <FileText className="mb-3 h-8 w-8 text-text-subtle" />
            <p className="text-body text-text-muted">
              This note is empty. Start writing to add a block.
            </p>
          </div>
        ) : (
          <div className="space-y-2.5">
            {note.blocks.map((block) => (
              <BlockView
                key={block.id}
                block={block}
                sourceNumbers={sourceNumbers}
                onCitationClick={onCitationClick}
                onRemoveLink={(linkId) => handleRemoveLink(block.id, linkId)}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
