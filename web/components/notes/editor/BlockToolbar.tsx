"use client";

import type { Editor } from "@tiptap/core";
import { cn } from "@/lib/utils";

/**
 * Turns the current block (or every block the selection touches) into a
 * heading, a bullet or body text.
 *
 * A toolbar rather than only markdown shortcuts: the shortcuts need a space
 * after the marker, which is easy to lose on a phone, and they never fire on
 * pasted text. This works on whatever is selected.
 */
export interface BlockToolbarProps {
  editor: Editor | null;
  className?: string;
}

type BlockName = "heading" | "bulletList" | "paragraph";

export function BlockToolbar({ editor, className }: BlockToolbarProps) {
  if (!editor) return null;

  const item = (label: string, target: BlockName, run: () => void) => {
    const active = editor.isActive(target);
    return (
      <button
        key={target}
        type="button"
        // Without this the click steals the selection before the command runs.
        onMouseDown={(event) => event.preventDefault()}
        onClick={run}
        aria-pressed={active}
        className={cn(
          "min-h-[44px] sm:min-h-0 sm:h-8 px-3 rounded text-body-sm transition-colors",
          active
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
      {item("Heading", "heading", () =>
        editor.chain().focus().toggleHeading({ level: 3 }).run(),
      )}
      {item("Bullet", "bulletList", () =>
        editor.chain().focus().toggleBulletList().run(),
      )}
      {item("Text", "paragraph", () =>
        editor.chain().focus().setParagraph().run(),
      )}
    </div>
  );
}
