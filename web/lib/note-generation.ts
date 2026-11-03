import { apiClient } from "./api-client";
import { makeLocalNote, useNotesStore, type LocalBlock, type LocalNote } from "./notes-store";
import { flushNoteSyncNow } from "./note-sync";
import { notifyNoteReady } from "./notify";
import type { GeneratedSectionNotes, NoteTopicEvent } from "@/types/notes";

/**
 * Background AI note generation (topic and chapter range).
 *
 * Both streams are driven by module-level async functions, not components, so a
 * note keeps generating after the panel unmounts — the student can close the
 * note, switch tabs, or keep reading. A placeholder note is inserted immediately
 * (status "generating") so the list shows it while it works; when the stream
 * completes the same note is filled in and the flag cleared. A reload cannot
 * resume a stream, so notes stranded as "generating" are flagged on hydration
 * (see notes-store).
 */

function patchNote(noteId: string, changes: Partial<LocalNote>): void {
  const current = useNotesStore.getState().getNote(noteId);
  if (!current) return; // deleted mid-flight — stop touching it
  useNotesStore.getState().saveNote({ ...current, ...changes });
}

// ── Topic generation ──────────────────────────────────────────

/** Map the `done` event's server-built blocks into local blocks. */
function blocksFromDone(
  done: Extract<NoteTopicEvent, { type: "done" }>,
): LocalBlock[] {
  return done.blocks.map((block) => ({
    id: crypto.randomUUID(),
    kind: block.kind,
    text: block.text,
    origin: block.origin ?? "ai",
    links: (block.links ?? []).map((link) => ({
      id: crypto.randomUUID(),
      section_id: link.section_id ?? null,
      anchor_heading_path: link.anchor_heading_path,
      page_start: link.page_start,
      page_end: link.page_end,
      excerpt: link.excerpt,
      status: link.status ?? "accepted",
      origin: link.origin,
    })),
  }));
}

/** Start generating a note from a topic. Returns the placeholder note id at once. */
export function startTopicNoteGeneration(bookId: string, topic: string): string {
  const note = makeLocalNote(bookId, {
    title: topic,
    source: "ai_generated",
    status: "generating",
    blocks: [],
  });
  useNotesStore.getState().saveNote(note);
  void runTopicGeneration(bookId, topic, note.id);
  return note.id;
}

async function runTopicGeneration(
  bookId: string,
  topic: string,
  noteId: string,
): Promise<void> {
  try {
    const stream = await apiClient.generateTopicNotes(bookId, topic);
    const reader = stream.getReader();
    let doneBlocks: LocalBlock[] | null = null;
    let doneTitle: string | null = null;
    let message: string | null = null;

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      const event = value as NoteTopicEvent | undefined;
      if (!event) continue;
      if (event.type === "done") {
        doneBlocks = blocksFromDone(event);
        doneTitle = event.title;
      } else if (event.type === "error" || event.type === "not_covered") {
        message = event.message;
      }
    }

    if (doneBlocks) {
      patchNote(noteId, {
        title: doneTitle ?? topic,
        blocks: doneBlocks,
        status: undefined,
        error: null,
      });
      void flushNoteSyncNow();
      notifyNoteReady(doneTitle ?? topic);
    } else {
      patchNote(noteId, { status: "error", error: message ?? "Couldn't generate notes" });
    }
  } catch (err) {
    patchNote(noteId, {
      status: "error",
      error: err instanceof Error ? err.message : "Couldn't generate notes",
    });
  }
}

// ── Chapter-range generation ──────────────────────────────────

/** Turn one section's generated notes into local blocks with citations. */
function sectionBlocks(section: GeneratedSectionNotes): LocalBlock[] {
  const blocks: LocalBlock[] = [
    {
      id: crypto.randomUUID(),
      kind: "heading",
      text: section.section_heading,
      origin: "ai",
      links: [],
    },
  ];

  for (const concept of section.concepts) {
    const text = [
      concept.name,
      concept.definition,
      concept.explanation,
      concept.example ? `Example: ${concept.example}` : "",
      concept.self_check ? `Self-check: ${concept.self_check}` : "",
    ]
      .filter(Boolean)
      .join("\n\n");

    blocks.push({
      id: crypto.randomUUID(),
      kind: "card",
      text,
      origin: "ai",
      links: [
        {
          id: crypto.randomUUID(),
          section_id: section.section_id,
          anchor_heading_path: section.section_heading,
          page_start: section.page_start,
          page_end: section.page_end,
          excerpt: concept.definition.slice(0, 240),
          status: "accepted",
          origin: "generated",
        },
      ],
    });
  }

  return blocks;
}

/** Start generating a note for a chapter range. Returns the placeholder note id. */
export function startChapterNoteGeneration(
  bookId: string,
  chapterStart: number,
  chapterEnd: number,
): string {
  const note = makeLocalNote(bookId, {
    title: `Chapters ${chapterStart}–${chapterEnd}`,
    source: "ai_generated",
    status: "generating",
    blocks: [],
  });
  useNotesStore.getState().saveNote(note);
  void runChapterGeneration(bookId, chapterStart, chapterEnd, note.id);
  return note.id;
}

async function runChapterGeneration(
  bookId: string,
  chapterStart: number,
  chapterEnd: number,
  noteId: string,
): Promise<void> {
  try {
    const stream = await apiClient.generateNotes(bookId, chapterStart, chapterEnd);
    const reader = stream.getReader();
    const blocks: LocalBlock[] = [];

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      const section = value as Partial<GeneratedSectionNotes> | undefined;
      if (!section || !section.section_heading || !Array.isArray(section.concepts)) {
        continue;
      }
      blocks.push(...sectionBlocks(section as GeneratedSectionNotes));
    }

    if (blocks.length === 0) {
      patchNote(noteId, {
        status: "error",
        error: "No notes were generated for that range.",
      });
      return;
    }

    patchNote(noteId, { blocks, status: undefined, error: null });
    void flushNoteSyncNow();
    notifyNoteReady();
  } catch (err) {
    patchNote(noteId, {
      status: "error",
      error: err instanceof Error ? err.message : "Couldn't generate notes",
    });
  }
}
