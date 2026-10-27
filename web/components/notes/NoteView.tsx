"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { AlertCircle, ArrowLeft, FileText } from "lucide-react";
import { cn } from "@/lib/utils";
import { apiClient } from "@/lib/api-client";
import { Loader } from "@/components/ui/loader";
import type { NoteBlock, NoteDetail, NoteLink } from "@/types/notes";

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
function buildSourceNumbers(blocks: NoteBlock[]): Map<string, number> {
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

function pagesLabel(link: NoteLink): string {
  return link.page_end !== link.page_start
    ? `pages ${link.page_start} to ${link.page_end}`
    : `page ${link.page_start}`;
}

function CitationChip({
  link,
  number,
  onCitationClick,
}: {
  link: NoteLink;
  number: number;
  onCitationClick?: (target: { page: number; text: string }) => void;
}) {
  // A link whose section was deleted keeps its stored pages but cannot jump.
  const isBroken = link.section_id === null;
  const accessibleName = `Source ${number}: ${link.anchor_heading_path}, ${pagesLabel(link)}`;

  if (isBroken) {
    return (
      <span
        aria-label={`${accessibleName} — source moved`}
        title={`${link.anchor_heading_path} · ${pagesLabel(link)} — source moved`}
        className="inline-flex items-center rounded border border-dashed border-border px-1 text-body-sm text-text-muted"
      >
        [{number}] source moved
      </span>
    );
  }

  return (
    <button
      type="button"
      aria-label={accessibleName}
      title={`${link.anchor_heading_path} · ${pagesLabel(link)}\n${link.excerpt}`}
      onClick={() =>
        onCitationClick?.({ page: link.page_start, text: link.excerpt })
      }
      className={cn(
        "inline-flex items-center rounded px-1 text-body-sm align-baseline transition-colors",
        link.status === "suggested"
          ? "border border-dashed border-accent/60 text-accent/80 hover:bg-accent/10"
          : "text-accent hover:bg-accent/10",
      )}
    >
      [{number}]
    </button>
  );
}

function BlockView({
  block,
  sourceNumbers,
  onCitationClick,
}: {
  block: NoteBlock;
  sourceNumbers: Map<string, number>;
  onCitationClick?: (target: { page: number; text: string }) => void;
}) {
  const links = block.links.filter((link) => link.status !== "dismissed");

  const chips = links.length > 0 && (
    <span className="ml-1 whitespace-nowrap">
      {links.map((link) => (
        <CitationChip
          key={link.id}
          link={link}
          number={sourceNumbers.get(link.section_id ?? link.anchor_heading_path) ?? 1}
          onCitationClick={onCitationClick}
        />
      ))}
    </span>
  );

  if (block.kind === "heading") {
    return (
      <p className="font-heading text-body font-semibold text-text-primary mt-4 first:mt-0">
        {block.text}
      </p>
    );
  }

  if (block.kind === "card") {
    return (
      <div className="rounded-md border border-border-subtle bg-bg-base p-3">
        <p className="text-body-sm text-text-primary whitespace-pre-wrap">
          {block.text}
          {chips}
        </p>
      </div>
    );
  }

  if (block.kind === "bullet") {
    return (
      <div className="flex gap-2">
        <span className="text-text-subtle shrink-0">•</span>
        <p className="text-body-sm text-text-primary whitespace-pre-wrap">
          {block.text}
          {chips}
        </p>
      </div>
    );
  }

  return (
    <p className="text-body-sm text-text-primary whitespace-pre-wrap">
      {block.text}
      {chips}
    </p>
  );
}

export function NoteView({
  noteId,
  onBack,
  onEdit,
  onCitationClick,
  className,
}: NoteViewProps) {
  const [note, setNote] = useState<NoteDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadNote = useCallback(async () => {
    setLoading(true);
    try {
      setNote(await apiClient.getNote(noteId));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't load this note");
    } finally {
      setLoading(false);
    }
  }, [noteId]);

  useEffect(() => {
    loadNote();
  }, [loadNote]);

  const sourceNumbers = useMemo(
    () => buildSourceNumbers(note?.blocks ?? []),
    [note],
  );

  return (
    <div className={cn("flex flex-col h-full", className)}>
      <div className="shrink-0 px-4 py-3 border-b border-border-subtle">
        <div className="flex items-center justify-between">
          <button
            onClick={onBack}
            className="flex items-center gap-1.5 text-body-sm text-text-muted hover:text-text-primary transition-colors"
          >
            <ArrowLeft className="h-3.5 w-3.5" strokeWidth={1.5} />
            All notes
          </button>
          {onEdit && !loading && !error && (
            <button
              onClick={onEdit}
              className="px-2 py-1 rounded text-body-sm text-text-muted hover:text-text-primary hover:bg-bg-elevated transition-colors"
            >
              Edit
            </button>
          )}
        </div>
        {note && (
          <p className="font-heading text-body-sm font-semibold text-text-primary mt-2">
            {note.title ?? "Untitled note"}
          </p>
        )}
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-3">
        {loading ? (
          <div className="flex items-center justify-center py-12">
            <Loader />
          </div>
        ) : error ? (
          <div className="flex flex-col items-center justify-center py-12 px-4 text-center">
            <AlertCircle className="h-8 w-8 text-text-subtle mb-3" />
            <p className="text-body-sm text-state-error mb-3">{error}</p>
            <button
              onClick={loadNote}
              className="px-3 py-1.5 rounded-md bg-bg-elevated text-body-sm text-text-primary hover:bg-bg-surface transition-colors"
            >
              Try again
            </button>
          </div>
        ) : !note || (note.blocks.length === 0 && !note.raw_text.trim()) ? (
          <div className="flex flex-col items-center justify-center py-12 px-4 text-center">
            <FileText className="h-8 w-8 text-text-subtle mb-3" />
            <p className="text-body text-text-muted">
              This note is empty. Start writing to add a block.
            </p>
          </div>
        ) : note.blocks.length === 0 ? (
          /* Notes written before blocks existed keep their text in one blob. */
          <div className="space-y-2">
            {note.raw_text
              .split(/\n{2,}/)
              .filter((paragraph) => paragraph.trim())
              .map((paragraph, index) => (
                <p
                  key={index}
                  className="text-body-sm text-text-primary whitespace-pre-wrap"
                >
                  {paragraph}
                </p>
              ))}
          </div>
        ) : (
          <div className="space-y-2">
            {note.blocks.map((block) => (
              <BlockView
                key={block.id}
                block={block}
                sourceNumbers={sourceNumbers}
                onCitationClick={onCitationClick}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
