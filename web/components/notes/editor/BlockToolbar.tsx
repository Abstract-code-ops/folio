"use client";

import type { Editor } from "@tiptap/core";
import { Link2 } from "lucide-react";
import { cn } from "@/lib/utils";

/**
 * Turns the current block (or every block the selection touches) into a
 * heading, a bullet or body text, or converts the selection into a study card.
 *
 * A toolbar rather than only markdown shortcuts: the shortcuts need a space
 * after the marker, which is easy to lose on a phone, and they never fire on
 * pasted text. This works on whatever is selected.
 */
export interface BlockToolbarProps {
  editor: Editor | null;
  /** "Cite" was pressed — the parent puts the editor into source-select mode. */
  onCite?: () => void;
  className?: string;
}

type BlockName = "heading" | "bulletList" | "paragraph" | "blockCard";

/**
 * Turn the block(s) at the cursor -- or the blocks a selection covers -- into a
 * single card that keeps all of their text. Replacing whole top-level blocks
 * (never an inline range) is deliberate: a card is a block, and dropping one
 * into the middle of a paragraph would mean splitting the paragraph around it.
 */
function convertSelectionToCard(editor: Editor): void {
  const { state } = editor;
  const { selection, schema } = state;
  const cardType = schema.nodes.blockCard;
  const paragraphType = schema.nodes.paragraph;
  if (!cardType || !paragraphType) return;

  // Never nest a card inside a card.
  if (editor.isActive("blockCard")) return;

  const buildCard = (text: string, blockId: string | null) => {
    const parts = text
      .split(/\n{2,}/)
      .map((part) => part.trim())
      .filter(Boolean);
    const paragraphs = (parts.length > 0 ? parts : [""]).map((part) =>
      paragraphType.create(null, part ? schema.text(part) : null),
    );
    return cardType.create({ blockId }, paragraphs);
  };

  const depth = 1;
  const { $from, $to } = selection;
  const start = $from.depth >= depth ? $from.before(depth) : selection.from;
  const end = $to.depth >= depth ? $to.after(depth) : selection.to;

  if (end <= start) {
    editor
      .chain()
      .focus()
      .insertContent({ type: "blockCard", content: [{ type: "paragraph" }] })
      .run();
    return;
  }

  const text = state.doc.textBetween(start, end, "\n\n");
  const singleBlock =
    $from.depth >= depth &&
    $to.depth >= depth &&
    $from.before(depth) === start &&
    $to.after(depth) === end;
  const blockId = singleBlock
    ? (($from.node(depth)?.attrs?.blockId as string | null | undefined) ?? null)
    : null;

  editor
    .chain()
    .focus()
    .command(({ tr }) => {
      tr.replaceWith(start, end, buildCard(text, blockId));
      return true;
    })
    .run();
}

export function BlockToolbar({ editor, onCite, className }: BlockToolbarProps) {
  if (!editor) return null;

  const inCard = editor.isActive("blockCard");
  const hasSelection = !editor.state.selection.empty;

  const item = (
    label: string,
    target: BlockName,
    run: () => void,
    disabled = false,
  ) => {
    const active = editor.isActive(target);
    return (
      <button
        key={target}
        type="button"
        // Without this the click steals the selection before the command runs.
        onMouseDown={(event) => event.preventDefault()}
        onClick={run}
        disabled={disabled}
        aria-pressed={active}
        className={cn(
          "min-h-[44px] sm:min-h-0 sm:h-8 px-3 rounded text-body-sm transition-colors",
          disabled
            ? "cursor-not-allowed text-text-muted opacity-40"
            : active
              ? "bg-accent/10 text-accent"
              : "text-text-muted hover:text-text-primary hover:bg-bg-elevated",
        )}
      >
        {label}
      </button>
    );
  };

  return (
    <div
      role="toolbar"
      aria-label="Block type"
      className={cn(
        "shrink-0 flex items-center gap-1 px-2 py-1 border-b border-border-subtle",
        className,
      )}
    >
      {/* Heading and bullet are disabled inside a card: a card is one prose
          block, so it holds paragraphs only. */}
      {item(
        "Heading",
        "heading",
        () => editor.chain().focus().toggleHeading({ level: 3 }).run(),
        inCard,
      )}
      {item(
        "Bullet",
        "bulletList",
        () => editor.chain().focus().toggleBulletList().run(),
        inCard,
      )}
      {item("Text", "paragraph", () =>
        editor.chain().focus().setParagraph().run(),
      )}
      {/* Converts the block(s) at the selection into a card, keeping their text.
          Remove a card by selecting it and pressing backspace. */}
      {item(
        "Card",
        "blockCard",
        () => convertSelectionToCard(editor),
        inCard,
      )}
      {/* Cite: select note text, click Cite, then select the source text in the
          reader. The reader resolves the page→section and attaches a link. */}
      {onCite && (
        <button
          type="button"
          onMouseDown={(event) => event.preventDefault()}
          onClick={onCite}
          disabled={!hasSelection}
          className={cn(
            "flex items-center gap-1.5 min-h-[44px] sm:min-h-0 sm:h-8 px-3 rounded text-body-sm transition-colors",
            hasSelection
              ? "text-text-muted hover:text-text-primary hover:bg-bg-elevated"
              : "cursor-not-allowed text-text-muted opacity-40",
          )}
        >
          <Link2 className="h-3.5 w-3.5" strokeWidth={1.5} />
          Cite
        </button>
      )}
    </div>
  );
}
