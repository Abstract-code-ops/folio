import type { JSONContent } from "@tiptap/core";
import type { BlockKind } from "@/types/notes";

/**
 * The editor document and the stored block list are two shapes of one thing.
 *
 * The document is what ProseMirror needs (nested lists, inline marks); the
 * blocks are what gets stored (a flat, ordered list). These functions are the
 * only place the two meet.
 *
 * Blocks are saved locally now, so every block carries a stable id: links attach
 * to block ids and survive editing. The id is stamped into the document by the
 * `BlockIdStamp` extension; here it is only read back (and regenerated as a
 * last resort, never as the normal path).
 */

/** A stored block without its links — links are merged by the editor later. */
export type DocBlock = { id: string; kind: BlockKind; text: string };

function newId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `b-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

/** Flatten a node's inline content to plain text. */
export function nodeText(node: JSONContent): string {
  if (typeof node.text === "string") return node.text;
  if (node.type === "hardBreak") return " ";
  return (node.content ?? []).map(nodeText).join("");
}

function isList(node: JSONContent): boolean {
  return node.type === "bulletList" || node.type === "orderedList";
}

function kindOf(node: JSONContent): BlockKind | null {
  switch (node.type) {
    case "heading":
      return "heading";
    case "paragraph":
      return "paragraph";
    default:
      return null;
  }
}

/**
 * Walk the document into blocks, carrying each block's id across.
 *
 * Two rules keep text from being lost or fused on save:
 *
 * 1. A list becomes one block per item. Emitting a whole list as one block
 *    would concatenate its items into a single run of text.
 * 2. An id is used at most once. If two blocks somehow claim the same id, the
 *    later one is treated as new rather than overwriting the earlier one's text.
 *
 * Empty nodes are skipped: ProseMirror always keeps a trailing empty paragraph,
 * and saving it would add an empty block on every pause.
 */
export function docToBlocks(doc: JSONContent): DocBlock[] {
  const blocks: DocBlock[] = [];
  const claimed = new Set<string>();

  const push = (kind: BlockKind, text: string, blockId: unknown) => {
    if (!text) return;
    let id = typeof blockId === "string" && blockId ? blockId : newId();
    if (claimed.has(id)) id = newId();
    claimed.add(id);
    blocks.push({ id, kind, text });
  };

  for (const node of doc.content ?? []) {
    if (isList(node)) {
      const items = node.content ?? [];
      for (const item of items) {
        push("bullet", nodeText(item).trim(), item.attrs?.blockId);
      }
      continue;
    }

    if (node.type === "blockCard") {
      // A card is one prose block: join its paragraphs with the blank lines the
      // read view splits on, so the whole card round-trips as a single block.
      const text = (node.content ?? [])
        .map((child) => nodeText(child).trim())
        .filter(Boolean)
        .join("\n\n");
      push("card", text, node.attrs?.blockId);
      continue;
    }

    const kind = kindOf(node);
    if (kind === null) continue;
    push(kind, nodeText(node).trim(), node.attrs?.blockId);
  }

  return blocks;
}

/**
 * Build the editor document from stored blocks.
 *
 * One block, one top-level node -- a bullet becomes a single-item list rather
 * than being merged with its neighbours, because merging would change the block
 * count and lose the ids (and therefore the links) on the save that follows.
 *
 * A `card` block becomes a `blockCard` container of paragraphs, not a paragraph:
 * editing one now saves it back as a card, so its kind survives an edit, and its
 * blank-line-separated prose is editable line by line.
 */
export function blocksToContent(
  blocks: { id: string; kind: BlockKind; text: string }[],
): JSONContent[] {
  return blocks.map((block) => {
    const attrs = { blockId: block.id };

    if (block.kind === "heading") {
      return {
        type: "heading",
        attrs: { level: 3, ...attrs },
        content: [{ type: "text", text: block.text }],
      };
    }

    if (block.kind === "bullet") {
      return {
        type: "bulletList",
        content: [
          {
            type: "listItem",
            attrs,
            content: [
              {
                type: "paragraph",
                content: [{ type: "text", text: block.text }],
              },
            ],
          },
        ],
      };
    }

    if (block.kind === "card") {
      // The stored text is prose split on blank lines; each part becomes its own
      // paragraph so the editor shows real lines and Enter adds another.
      const parts = block.text
        .split(/\n{2,}/)
        .map((part) => part.trim())
        .filter(Boolean);
      return {
        type: "blockCard",
        attrs,
        content: (parts.length > 0 ? parts : [""]).map((part) => ({
          type: "paragraph",
          content: part ? [{ type: "text", text: part }] : [],
        })),
      };
    }

    return {
      type: "paragraph",
      attrs,
      content: [{ type: "text", text: block.text }],
    };
  });
}
