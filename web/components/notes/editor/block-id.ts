import {
  Extension,
  mergeAttributes,
  Node,
  textblockTypeInputRule,
  wrappingInputRule,
} from "@tiptap/core";
import { Plugin, PluginKey } from "@tiptap/pm/state";
import { BulletList } from "@tiptap/extension-bullet-list";
import { Heading } from "@tiptap/extension-heading";
import { ListItem } from "@tiptap/extension-list-item";
import { Paragraph } from "@tiptap/extension-paragraph";

/** The one heading level a note produces; the model has a single heading kind. */
const NOTE_HEADING_LEVEL = 3;

function newId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `b-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

/**
 * The block nodes carry a `blockId`.
 *
 * This is the whole reason links survive editing. A note's citations hang off
 * block rows, and autosave matches blocks by id; if the editor could not say
 * "this is still block X", every save would replace the rows and every link
 * would be cascaded away with them.
 *
 * `keepOnSplit: false` is load-bearing. Splitting a paragraph (pressing Enter in
 * the middle of one) copies node attributes into the new node, so without it
 * both halves claim the same id: the save updates that one block twice and the
 * first half's text is silently overwritten. A new block gets a fresh id from
 * `BlockIdStamp` instead, which is what "the citation belongs to the text that
 * was split" means in practice.
 */
const blockIdAttribute = {
  default: null as string | null,
  keepOnSplit: false,
  parseHTML: (element: HTMLElement) => element.getAttribute("data-block-id"),
  renderHTML: (attributes: Record<string, unknown>) =>
    attributes.blockId ? { "data-block-id": attributes.blockId as string } : {},
};

export const BlockParagraph = Paragraph.extend({
  addAttributes() {
    return { blockId: blockIdAttribute };
  },
});

export const BlockHeading = Heading.extend({
  addAttributes() {
    return { ...this.parent?.(), blockId: blockIdAttribute };
  },
  addInputRules() {
    // The stock rule is built as /^(#{min(levels)},level)\s$/, so with a single
    // configured level it only accepts exactly that many hashes -- `# ` did
    // nothing. Any run of hashes produces the note's one heading kind.
    return [
      textblockTypeInputRule({
        find: /^(#{1,6})\s$/,
        type: this.type,
        getAttributes: { level: NOTE_HEADING_LEVEL },
      }),
    ];
  },
});

export const BlockBulletList = BulletList.extend({
  addInputRules() {
    // Declared rather than inherited so the behaviour is visible here: `- `,
    // `* ` and `+ ` all start a bullet.
    return [wrappingInputRule({ find: /^\s*([-+*])\s$/, type: this.type })];
  },
});

/** A bullet's id lives on its list item, since each item is its own block. */
export const BlockListItem = ListItem.extend({
  addAttributes() {
    return { ...this.parent?.(), blockId: blockIdAttribute };
  },
});

/**
 * A study card. Cards are prose (docs/notes-design-notes.md): one stored text
 * column holds concept/definition/example, and the read view splits it on blank
 * lines. In the editor that maps to a container of paragraphs, which is what
 * lets Enter start a new line inside a card. It renders `data-kind="card"` so
 * the editor can style it and the block mapper can tell it from a paragraph.
 *
 * Paragraph-only on purpose: a card is one prose block, not a nesting of other
 * block kinds. Without this node a saved card came back as a paragraph and
 * quietly lost its kind.
 */
export const BlockCard = Node.create({
  name: "blockCard",
  group: "block",
  content: "paragraph+",
  defining: true,
  addAttributes() {
    return { blockId: blockIdAttribute };
  },
  parseHTML() {
    return [{ tag: 'div[data-kind="card"]' }];
  },
  renderHTML({ HTMLAttributes }) {
    return ["div", mergeAttributes(HTMLAttributes, { "data-kind": "card" }), 0];
  },
});

/**
 * Stamp a client id on any block node that lacks one, as soon as it is created.
 *
 * Blocks are saved locally now, and links attach to block ids, so a block made
 * by splitting or by the toolbar must have a stable id before it is ever saved.
 * Doing it in an appendTransaction (not at save time) means the id is written
 * into the document once and read back unchanged on every later save.
 */
export const BlockIdStamp = Extension.create({
  name: "blockIdStamp",
  addProseMirrorPlugins() {
    return [
      new Plugin({
        key: new PluginKey("blockIdStamp"),
        appendTransaction: (transactions, _oldState, newState) => {
          if (transactions.some((tr) => tr.getMeta("blockIdStamp"))) return null;
          const { tr } = newState;
          let changed = false;
          newState.doc.descendants((node, pos) => {
            if (
              node.isBlock &&
              node.type.name !== "doc" &&
              node.type.spec.attrs?.blockId &&
              node.attrs.blockId == null
            ) {
              tr.setNodeAttribute(pos, "blockId", newId());
              changed = true;
            }
          });
          return changed ? tr.setMeta("blockIdStamp", true) : null;
        },
      }),
    ];
  },
});
