import { beforeEach, describe, expect, it } from "vitest";
import {
  citedSectionIds,
  hasContent,
  makeLocalNote,
  useNotesStore,
  type LocalBlock,
  type LocalLink,
} from "./notes-store";

function block(partial: Partial<LocalBlock> = {}): LocalBlock {
  return {
    id: "b",
    kind: "paragraph",
    text: "",
    origin: "typed",
    links: [],
    ...partial,
  };
}

function link(
  sectionId: string | null,
  status: LocalLink["status"] = "accepted",
): LocalLink {
  return {
    id: `l-${sectionId ?? "null"}-${status}`,
    section_id: sectionId,
    anchor_heading_path: "H",
    page_start: 1,
    page_end: 1,
    excerpt: "e",
    status,
    origin: "manual",
  };
}

describe("hasContent", () => {
  it("is false with no blocks", () => {
    expect(hasContent(makeLocalNote("book"))).toBe(false);
  });

  it("is false when every block is whitespace", () => {
    const note = makeLocalNote("book", { blocks: [block({ text: "   \n " })] });
    expect(hasContent(note)).toBe(false);
  });

  it("is true when any block has text", () => {
    const note = makeLocalNote("book", {
      blocks: [block({ text: "" }), block({ id: "b2", text: "hi" })],
    });
    expect(hasContent(note)).toBe(true);
  });
});

describe("citedSectionIds", () => {
  it("returns distinct accepted section ids, ignoring dismissed and null", () => {
    const note = makeLocalNote("book", {
      blocks: [
        block({
          links: [
            link("s1"),
            link("s1"),
            link("s2"),
            link("s3", "dismissed"),
            link(null),
          ],
        }),
      ],
    });
    expect(citedSectionIds(note).sort()).toEqual(["s1", "s2"]);
  });
});

describe("makeLocalNote", () => {
  it("defaults to an empty typed note with a generated id", () => {
    const note = makeLocalNote("book");
    expect(note.bookId).toBe("book");
    expect(note.blocks).toEqual([]);
    expect(note.source).toBe("typed");
    expect(note.id).toBeTruthy();
  });

  it("honours the partial override", () => {
    const note = makeLocalNote("book", { id: "x", title: "T" });
    expect(note.id).toBe("x");
    expect(note.title).toBe("T");
  });
});

describe("useNotesStore", () => {
  beforeEach(() => {
    useNotesStore.setState({ notes: {} });
  });

  it("lists a book's notes newest first and excludes other books", () => {
    const a = makeLocalNote("book", { id: "a", updatedAt: 1000 });
    const b = makeLocalNote("book", { id: "b", updatedAt: 2000 });
    const other = makeLocalNote("other", { id: "c", updatedAt: 3000 });
    useNotesStore.setState({ notes: { a, b, c: other } });

    expect(useNotesStore.getState().listNotes("book").map((n) => n.id)).toEqual([
      "b",
      "a",
    ]);
  });

  it("saves (upsert) and reads a note", () => {
    useNotesStore.getState().saveNote(makeLocalNote("book", { id: "a" }));
    expect(useNotesStore.getState().getNote("a")?.id).toBe("a");
  });

  it("renames a note", () => {
    useNotesStore.getState().saveNote(makeLocalNote("book", { id: "a" }));
    useNotesStore.getState().renameNote("a", "New title");
    expect(useNotesStore.getState().getNote("a")?.title).toBe("New title");
  });

  it("deletes a note", () => {
    useNotesStore.getState().saveNote(makeLocalNote("book", { id: "a" }));
    useNotesStore.getState().deleteNote("a");
    expect(useNotesStore.getState().getNote("a")).toBeUndefined();
  });

  it("round-trips through export/import", () => {
    useNotesStore
      .getState()
      .saveNote(makeLocalNote("book", { id: "a", blocks: [block({ text: "hi" })] }));
    const json = useNotesStore.getState().exportNotes();

    useNotesStore.setState({ notes: {} });
    useNotesStore.getState().importNotes(json);

    expect(useNotesStore.getState().getNote("a")?.blocks[0].text).toBe("hi");
  });

  it("importing malformed JSON leaves the store untouched", () => {
    useNotesStore.getState().saveNote(makeLocalNote("book", { id: "a" }));
    useNotesStore.getState().importNotes("{not json");
    expect(useNotesStore.getState().getNote("a")).toBeDefined();
  });
});
