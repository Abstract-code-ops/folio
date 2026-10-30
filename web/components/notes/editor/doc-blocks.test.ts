import { describe, expect, it } from "vitest";
import type { NoteBlock } from "@/types/notes";
import { blocksToContent, docToBlocks, nodeText } from "./doc-blocks";

/**
 * These converters are the only place the editor document and the stored block
 * list meet, and they already caused one data-loss bug (a card saved as a
 * paragraph). The tests pin the round trip so it cannot regress silently.
 */

function makeBlock(
  overrides: Partial<NoteBlock> & Pick<NoteBlock, "kind" | "text">,
): NoteBlock {
  return {
    id: overrides.id ?? "blk",
    position: overrides.position ?? 0,
    kind: overrides.kind,
    text: overrides.text,
    origin: overrides.origin ?? "typed",
    links: overrides.links ?? [],
  };
}

function para(text: string, blockId: string | null = null) {
  return {
    type: "paragraph",
    attrs: { blockId },
    content: text ? [{ type: "text", text }] : [],
  };
}

describe("nodeText", () => {
  it("flattens inline content to plain text and turns hard breaks into spaces", () => {
    expect(
      nodeText({
        type: "paragraph",
        content: [
          { type: "text", text: "a" },
          { type: "hardBreak" },
          { type: "text", text: "b" },
        ],
      }),
    ).toBe("a b");
  });
});

describe("docToBlocks", () => {
  it("maps a paragraph to a paragraph block and carries its id", () => {
    const blocks = docToBlocks({ type: "doc", content: [para("hello", "id-1")] });
    expect(blocks).toEqual([{ id: "id-1", kind: "paragraph", text: "hello" }]);
  });

  it("maps a heading node to a heading block", () => {
    const blocks = docToBlocks({
      type: "doc",
      content: [
        {
          type: "heading",
          attrs: { level: 3, blockId: "h" },
          content: [{ type: "text", text: "Title" }],
        },
      ],
    });
    expect(blocks).toEqual([{ id: "h", kind: "heading", text: "Title" }]);
  });

  it("maps each bullet item in a list to its own bullet block, using each item's id", () => {
    const blocks = docToBlocks({
      type: "doc",
      content: [
        {
          type: "bulletList",
          content: [
            { type: "listItem", attrs: { blockId: "b1" }, content: [para("one")] },
            { type: "listItem", attrs: { blockId: "b2" }, content: [para("two")] },
          ],
        },
      ],
    });
    expect(blocks).toEqual([
      { id: "b1", kind: "bullet", text: "one" },
      { id: "b2", kind: "bullet", text: "two" },
    ]);
  });

  it("maps a blockCard (paragraphs) to one card block, joining on blank lines", () => {
    const blocks = docToBlocks({
      type: "doc",
      content: [
        {
          type: "blockCard",
          attrs: { blockId: "c" },
          content: [
            { type: "paragraph", content: [{ type: "text", text: "SSTable" }] },
            {
              type: "paragraph",
              content: [{ type: "text", text: "A sorted string table." }],
            },
            {
              type: "paragraph",
              content: [{ type: "text", text: "Example: an LSM tree" }],
            },
          ],
        },
      ],
    });
    expect(blocks).toEqual([
      {
        id: "c",
        kind: "card",
        text: "SSTable\n\nA sorted string table.\n\nExample: an LSM tree",
      },
    ]);
  });

  it("skips empty nodes so a trailing empty paragraph is never saved", () => {
    const blocks = docToBlocks({ type: "doc", content: [para("only"), para("")] });
    expect(blocks).toHaveLength(1);
    expect(blocks[0]).toMatchObject({ kind: "paragraph", text: "only" });
    expect(blocks[0].id).toBeTruthy();
  });

  it("skips an empty card so it creates no block", () => {
    const blocks = docToBlocks({
      type: "doc",
      content: [{ type: "blockCard", attrs: { blockId: "c" }, content: [] }],
    });
    expect(blocks).toEqual([]);
  });

  it("claims an id at most once so a duplicated id cannot overwrite text", () => {
    const blocks = docToBlocks({
      type: "doc",
      content: [para("first", "dup"), para("second", "dup")],
    });
    const ids = blocks.map((block) => block.id);
    expect(ids[0]).toBe("dup");
    expect(ids[1]).not.toBe("dup");
    expect(new Set(ids).size).toBe(2);
  });
});

describe("blocksToContent", () => {
  it("maps a card block to a blockCard of paragraphs, not a paragraph", () => {
    const [node] = blocksToContent([
      makeBlock({ id: "c", kind: "card", text: "Concept\n\nExample: x" }),
    ]);
    expect(node.type).toBe("blockCard");
    expect(node.attrs).toMatchObject({ blockId: "c" });
    expect((node.content ?? []).map((child) => child.type)).toEqual([
      "paragraph",
      "paragraph",
    ]);
    expect((node.content ?? [])[0]).toMatchObject({
      content: [{ type: "text", text: "Concept" }],
    });
  });

  it("maps heading, bullet and paragraph kinds to their editor nodes", () => {
    const content = blocksToContent([
      makeBlock({ id: "h", kind: "heading", text: "H" }),
      makeBlock({ id: "b", kind: "bullet", text: "B" }),
      makeBlock({ id: "p", kind: "paragraph", text: "P" }),
    ]);
    expect(content.map((node) => node.type)).toEqual([
      "heading",
      "bulletList",
      "paragraph",
    ]);
  });
});

describe("round trip: blocksToContent → docToBlocks", () => {
  it("preserves kind, text and id for every kind, including multi-paragraph card text", () => {
    const input: NoteBlock[] = [
      makeBlock({ id: "h", kind: "heading", text: "Intro" }),
      makeBlock({ id: "p", kind: "paragraph", text: "Body text" }),
      makeBlock({ id: "b", kind: "bullet", text: "A point" }),
      makeBlock({
        id: "c",
        kind: "card",
        text: "Concept\n\nDefinition here.\n\nExample: concrete",
      }),
    ];

    const back = docToBlocks({ type: "doc", content: blocksToContent(input) });

    expect(back.map((block) => ({ id: block.id, kind: block.kind, text: block.text }))).toEqual(
      input.map((block) => ({ id: block.id, kind: block.kind, text: block.text })),
    );
  });
});
