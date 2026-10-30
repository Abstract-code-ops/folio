import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { makeLocalNote, useNotesStore } from "./notes-store";
import { createNoteSync, toBatchNote } from "./note-sync";

function aNote(bookId = "b1") {
  return makeLocalNote(bookId, {
    blocks: [
      { id: "blk-1", kind: "paragraph", text: "Hello", origin: "typed", links: [] },
    ],
  });
}

describe("note-sync", () => {
  beforeEach(() => {
    useNotesStore.setState({ notes: {}, pendingDeletes: [] });
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("coalesces a burst and flushes on demand", async () => {
    const save = vi.fn().mockResolvedValue(undefined);
    const sync = createNoteSync({ save });
    const note = aNote();
    useNotesStore.getState().saveNote(note);

    sync.markDirty(note.id);
    sync.markDirty(note.id);
    sync.markDirty(note.id);

    expect(save).not.toHaveBeenCalled();
    await sync.flush();
    expect(save).toHaveBeenCalledTimes(1);
    expect(save.mock.calls[0][0]).toHaveLength(1);
    expect(save.mock.calls[0][0][0].id).toBe(note.id);
  });

  it("does not flush per edit — only at the safety backstop", async () => {
    const save = vi.fn().mockResolvedValue(undefined);
    const sync = createNoteSync({ save, safetyMs: 60000 });
    const note = aNote();
    useNotesStore.getState().saveNote(note);

    sync.markDirty(note.id);
    await vi.advanceTimersByTimeAsync(2000);
    expect(save).not.toHaveBeenCalled(); // no debounce mid-edit
    await vi.advanceTimersByTimeAsync(59000);
    expect(save).toHaveBeenCalledTimes(1); // safety backstop
  });

  it("flushes immediately on demand", async () => {
    const save = vi.fn().mockResolvedValue(undefined);
    const sync = createNoteSync({ save });
    const note = aNote();
    useNotesStore.getState().saveNote(note);

    sync.markDirty(note.id);
    await sync.flush();

    expect(save).toHaveBeenCalledTimes(1);
  });

  it("does not sync an emptied note", async () => {
    const save = vi.fn().mockResolvedValue(undefined);
    const sync = createNoteSync({ save });
    const note = makeLocalNote("b1");
    useNotesStore.getState().saveNote(note);

    sync.markDirty(note.id);
    await sync.flush();

    expect(save).not.toHaveBeenCalled();
  });

  it("keeps notes dirty on a failed save and retries", async () => {
    const save = vi
      .fn()
      .mockRejectedValueOnce(new Error("down"))
      .mockResolvedValue(undefined);
    const sync = createNoteSync({ save, deleteDebounceMs: 1500 });
    const note = aNote();
    useNotesStore.getState().saveNote(note);

    sync.markDirty(note.id);
    await sync.flush(); // fails
    expect(save).toHaveBeenCalledTimes(1);

    await vi.advanceTimersByTimeAsync(1600); // retry succeeds
    expect(save).toHaveBeenCalledTimes(2);
  });

  it("flushes pending deletes and clears them", async () => {
    const save = vi.fn().mockResolvedValue(undefined);
    const sync = createNoteSync({ save });
    const note = aNote();
    useNotesStore.getState().saveNote(note);
    useNotesStore.getState().deleteNote(note.id);

    await sync.flush();

    expect(save).toHaveBeenCalledTimes(1);
    const [, deleted] = save.mock.calls[0];
    expect(deleted).toContain(note.id);
    expect(useNotesStore.getState().pendingDeletes).toEqual([]);
  });

  it("toBatchNote maps local → server payload", () => {
    const note = aNote("bookX");
    const batch = toBatchNote(note);
    expect(batch.book_id).toBe("bookX");
    expect(batch.source).toBe("pasted"); // local "typed" maps to "pasted"
    expect(batch.blocks[0].id).toBe("blk-1");
    expect(batch.blocks[0].links).toEqual([]);
  });
});
