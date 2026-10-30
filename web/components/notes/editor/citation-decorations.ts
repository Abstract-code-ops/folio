import { Extension } from "@tiptap/core";
import { Plugin, PluginKey } from "@tiptap/pm/state";
import { Decoration, DecorationSet } from "@tiptap/pm/view";
import type { Node as PMNode } from "@tiptap/pm/model";
import type { LocalLink } from "@/lib/notes-store";

/**
 * Underline cited text inside the editor, matching the read view.
 *
 * Links are metadata (they hang off block ids), so this is render-only: the
 * saved document is untouched. A link with a `quote` underlines just that phrase
 * (so a phrase inside a card can be cited); a link without one underlines the
 * whole block.
 */

/** Meta key the editor dispatches when link metadata changes but the doc did not. */
export const CITATION_REFRESH_META = "citationDecorationsRefresh";

const KEY = new PluginKey("citationDecorations");

function buildDecorations(
  doc: PMNode,
  linksByBlock: Map<string, LocalLink[]>,
): DecorationSet {
  const decos: Decoration[] = [];

  doc.descendants((node, pos) => {
    if (!node.isBlock || node.type.name === "doc") return;
    const blockId = node.attrs?.blockId as string | null | undefined;
    if (!blockId) return;

    const visible = (linksByBlock.get(blockId) ?? []).filter(
      (link) => link.status !== "dismissed",
    );
    if (visible.length === 0) return;

    const wholeCited = visible.some((link) => !link.quote);
    const quotes = visible
      .map((link) => link.quote)
      .filter((quote): quote is string => !!quote);

    node.descendants((child, relPos) => {
      if (!child.isText || !child.text) return;
      const text = child.text;
      const from = pos + relPos;

      if (wholeCited) {
        decos.push(
          Decoration.inline(from, from + text.length, { class: "note-editor-cited" }),
        );
        return;
      }

      for (const quote of quotes) {
        let index = text.indexOf(quote);
        while (index >= 0) {
          decos.push(
            Decoration.inline(from + index, from + index + quote.length, {
              class: "note-editor-cited",
            }),
          );
          index = text.indexOf(quote, index + quote.length);
        }
      }
    });
  });

  return DecorationSet.create(doc, decos);
}

export interface CitationDecorationsOptions {
  getLinks: () => Map<string, LocalLink[]>;
}

export const CitationDecorations = Extension.create<CitationDecorationsOptions>({
  name: "citationDecorations",

  addOptions() {
    return { getLinks: () => new Map() };
  },

  addProseMirrorPlugins() {
    const getLinks = this.options.getLinks;
    return [
      new Plugin({
        key: KEY,
        state: {
          init: (_config, state) => buildDecorations(state.doc, getLinks()),
          apply: (tr, value) =>
            tr.docChanged || tr.getMeta(CITATION_REFRESH_META)
              ? buildDecorations(tr.doc, getLinks())
              : value,
        },
        props: {
          decorations(state) {
            return KEY.getState(state);
          },
        },
      }),
    ];
  },
});
