import { textblockTypeInputRule, wrappingInputRule } from "@tiptap/core";
import { BulletList } from "@tiptap/extension-bullet-list";
import { Heading } from "@tiptap/extension-heading";
import { Paragraph } from "@tiptap/extension-paragraph";

/** The one heading level a note produces; the model has a single heading kind. */
const NOTE_HEADING_LEVEL = 3;

/**
 * The three block nodes carry a `blockId`.
 *
 * This is the whole reason links survive editing. A note's citations hang off
 * block rows, and autosave matches blocks by id; if the editor could not say
 * "this is still block X", every save would replace the rows and every link
 * would be cascaded away with them.
 *
 * `keepOnSplit: false` is load-bearing. Splitting a paragraph (pressing Enter in
 * the middle of one) copies node attributes into the new node, so without it
 * both halves claim the same row: the save updates that one row twice and the
 * first half's text is silently overwritten. A new block has no id and is
 * inserted, which is what "the citation belongs to the text that was split"
 * means in practice.
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
  addAttributes() {
    return { ...this.parent?.(), blockId: blockIdAttribute };
  },
  addInputRules() {
    // Declared rather than inherited so the behaviour is visible here: `- `,
    // `* ` and `+ ` all start a bullet.
    return [wrappingInputRule({ find: /^\s*([-+*])\s$/, type: this.type })];
  },
});
