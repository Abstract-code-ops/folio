import type { JSONContent } from "@tiptap/core";
import type { BlockKind, NoteBlock, NoteBlockDraft } from "@/types/notes";

/**
 * The editor document and the stored block list are two shapes of one thing.
 *
 * The document is what ProseMirror needs (nested lists, inline marks); the
 * blocks are what the database stores (a flat, ordered list). These functions
 * are the only place the two meet.
 */

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
 * 2. An id is used at most once. If two blocks somehow claim the same row, the
 *    later one is treated as new rather than overwriting the earlier one's text.
 *
 * Empty nodes are skipped: ProseMirror always keeps a trailing empty paragraph,
 * and saving it would add an empty block on every pause.
 */
export function docToBlocks(doc: JSONContent): NoteBlockDraft[] {
  const blocks: NoteBlockDraft[] = [];
  const claimed = new Set<string>();

  const push = (kind: BlockKind, text: string, blockId: unknown) => {
    if (!text) return;
    const id =
      typeof blockId === "string" && blockId && !claimed.has(blockId)
        ? blockId
        : undefined;
    if (id) claimed.add(id);
    blocks.push({ id, kind, text });
  };

  for (const node of doc.content ?? []) {
    if (isList(node)) {
      const items = node.content ?? [];
      items.forEach((item, index) => {
        push(
          "bullet",
          nodeText(item).trim(),
          index === 0 ? node.attrs?.blockId : undefined,
        );
      });
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
 * A `card` block is edited as a plain paragraph; the read view is where the card
 * styling lives. Editing one therefore saves it back as a paragraph.
 */
export function blocksToContent(blocks: NoteBlock[]): JSONContent[] {
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
        attrs,
        content: [
          {
            type: "listItem",
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

    return {
      type: "paragraph",
      attrs,
      content: [{ type: "text", text: block.text }],
    };
  });
}
