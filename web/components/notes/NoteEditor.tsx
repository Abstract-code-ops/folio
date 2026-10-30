"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { Editor } from "@tiptap/core";
import { EditorContent, useEditor } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import { Placeholder } from "@tiptap/extension-placeholder";
import { ArrowLeft, Check } from "lucide-react";
import { cn } from "@/lib/utils";
import { Loader } from "@/components/ui/loader";
import {
  hasContent,
  makeLocalNote,
  useNotesStore,
  type LocalBlock,
  type LocalNote,
} from "@/lib/notes-store";
import { useCiteBridge } from "@/lib/cite-bridge";
import { flushNoteSyncNow } from "@/lib/note-sync";
import {
  BlockBulletList,
  BlockCard,
  BlockHeading,
  BlockIdStamp,
  BlockListItem,
  BlockParagraph,
} from "./editor/block-id";
import { BlockToolbar } from "./editor/BlockToolbar";
import { blocksToContent, docToBlocks } from "./editor/doc-blocks";
import { CITATION_REFRESH_META, CitationDecorations } from "./editor/citation-decorations";

/** Quiet time before an autosave. Long enough to finish a sentence. */
const AUTOSAVE_DELAY_MS = 2000;

/** The stored-block id at the cursor (a bullet's id lives on its list item). */
function blockIdAtSelection(editor: Editor): string | null {
  const { $from } = editor.state.selection;
  if ($from.depth < 1) return null;
  const top = $from.node(1);
  if (top.type.name === "bulletList") {
    const item = $from.depth >= 2 ? $from.node(2) : null;
    return (item?.attrs?.blockId as string | null) ?? null;
  }
  return (top.attrs?.blockId as string | null) ?? null;
}

export interface NoteEditorProps {
  bookId: string;
  /** `null` means a brand-new draft — nothing is written until it has content. */
  noteId: string | null;
  /** Leave the editor; the read view reloads the note. */
  onDone: () => void;
  /** Called after a successful save. */
  onSaved?: (note: LocalNote) => void;
  className?: string;
}

type SaveState = "idle" | "pending" | "saving" | "saved" | "error";

export function NoteEditor({
  bookId,
  noteId,
  onDone,
  onSaved,
  className,
}: NoteEditorProps) {
  const [ready, setReady] = useState(false);
  const [state, setState] = useState<SaveState>("idle");
  const [saveError, setSaveError] = useState<string | null>(null);

  // The working note lives in a ref so the debounced save never reads a stale
  // closure; `noteId` is only consulted once, to seed the editor.
  const noteRef = useRef<LocalNote>(makeLocalNote(bookId));
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const saveSeq = useRef(0);
  const dirty = useRef(false);
  const seeded = useRef(false);

  const extensions = useMemo(
    () => [
      // Only the nodes a note can hold: paragraphs, headings, one-level bullets
      // and cards. Lists of lists, quotes and code blocks are noise in study
      // notes, and each one is another shape the block mapper must handle.
      StarterKit.configure({
        paragraph: false,
        heading: false,
        bulletList: false,
        orderedList: false,
        listItem: false,
        blockquote: false,
        codeBlock: false,
        horizontalRule: false,
        link: false,
        underline: false,
      }),
      BlockParagraph,
      BlockHeading.configure({ levels: [3] }),
      BlockBulletList,
      BlockListItem,
      BlockCard,
      BlockIdStamp,
      CitationDecorations.configure({
        getLinks: () =>
          new Map(noteRef.current.blocks.map((block) => [block.id, block.links])),
      }),
      Placeholder.configure({ placeholder: "Start writing…" }),
    ],
    [],
  );

  const persist = useCallback(
    async (editor: Editor) => {
      if (!dirty.current) return;
      const seq = ++saveSeq.current;
      setState("saving");
      setSaveError(null);
      try {
        const docBlocks = docToBlocks(editor.getJSON());

        // Links attach to block ids, so they must be carried across a save even
        // when their block's text was split/edited away. Merge by id.
        const byId = new Map(
          noteRef.current.blocks.map((block) => [block.id, block]),
        );
        const blocks: LocalBlock[] = docBlocks.map((block) => ({
          id: block.id,
          kind: block.kind,
          text: block.text,
          origin: byId.get(block.id)?.origin ?? "typed",
          links: byId.get(block.id)?.links ?? [],
        }));

        // An empty draft writes nothing: the "empty note saved itself" bug was a
        // server row that should never have existed. Locally, just don't save.
        if (!blocks.some((block) => block.text.trim())) {
          if (seq === saveSeq.current) {
            dirty.current = false;
            setState("idle");
          }
          return;
        }

        const saved: LocalNote = {
          ...noteRef.current,
          bookId,
          blocks,
          updatedAt: Date.now(),
        };
        useNotesStore.getState().saveNote(saved);
        noteRef.current = saved;

        if (seq !== saveSeq.current) return;
        dirty.current = false;
        setState("saved");
        onSaved?.(saved);
      } catch (err) {
        if (seq !== saveSeq.current) return;
        setState("error");
        setSaveError(
          err instanceof Error ? err.message : "Couldn't save this note",
        );
      }
    },
    [bookId, onSaved],
  );

  const scheduleSave = useCallback(
    (editor: Editor) => {
      if (timer.current) clearTimeout(timer.current);
      timer.current = setTimeout(() => {
        void persist(editor);
      }, AUTOSAVE_DELAY_MS);
    },
    [persist],
  );

  const editor = useEditor({
    extensions,
    // A doc must hold at least one block, so an empty editor is one empty
    // paragraph rather than an empty array (which the schema rejects).
    content: { type: "doc", content: [{ type: "paragraph" }] },
    immediatelyRender: false,
    shouldRerenderOnTransaction: true,
    editorProps: {
      attributes: {
        class: "folio-note-editor",
        "aria-label": "Note body",
      },
    },
    onUpdate: ({ editor: instance }) => {
      dirty.current = true;
      setState("pending");
      scheduleSave(instance);
    },
  });

  const [citing, setCiting] = useState(false);

  const cite = useCallback(() => {
    if (!editor) return;
    const { state } = editor;
    const quote = state.selection.empty
      ? null
      : state.doc.textBetween(state.selection.from, state.selection.to, " ");
    useCiteBridge.getState().setCiteRequest({
      noteId: noteRef.current.id,
      blockId: blockIdAtSelection(editor),
      quote,
    });
    setCiting(true);
  }, [editor]);

  // The reader resolves a cite request into a ready link; attach it to the
  // note's block. Links are metadata, so the document itself is unchanged.
  const resolvedLink = useCiteBridge((s) => s.resolvedLink);
  useEffect(() => {
    if (!resolvedLink || resolvedLink.noteId !== noteRef.current.id) return;
    const note = noteRef.current;
    if (resolvedLink.blockId) {
      const target = note.blocks.find((block) => block.id === resolvedLink.blockId);
      if (target?.links.some((link) => link.excerpt === resolvedLink.link.excerpt)) {
        // Already cited to this block — don't stack a duplicate.
        useCiteBridge.getState().setResolvedLink(null);
        setCiting(false);
        return;
      }
      noteRef.current = {
        ...note,
        blocks: note.blocks.map((block) =>
          block.id === resolvedLink.blockId
            ? { ...block, links: [...block.links, resolvedLink.link] }
            : block,
        ),
      };
    } else {
      noteRef.current = {
        ...note,
        blocks: [
          ...note.blocks,
          {
            id: crypto.randomUUID(),
            kind: "paragraph",
            text: "",
            origin: "typed",
            links: [resolvedLink.link],
          },
        ],
      };
    }
    if (hasContent(noteRef.current)) {
      useNotesStore.getState().saveNote(noteRef.current);
    }
    useCiteBridge.getState().setResolvedLink(null);
    setCiting(false);
    // Refresh the editor's citation decorations — only link metadata changed.
    editor?.view.dispatch(editor.state.tr.setMeta(CITATION_REFRESH_META, true));
  }, [resolvedLink]);

  // Seed once, without emitting an update — otherwise setting the initial
  // content would look like an edit and immediately save over the note.
  useEffect(() => {
    if (!editor || seeded.current) return;
    seeded.current = true;

    const existing = noteId ? useNotesStore.getState().getNote(noteId) : undefined;
    noteRef.current = existing ?? makeLocalNote(bookId);

    const content =
      noteRef.current.blocks.length > 0
        ? blocksToContent(noteRef.current.blocks)
        : [{ type: "paragraph" }];

    editor.commands.setContent(
      { type: "doc", content },
      { emitUpdate: false },
    );
    editor.commands.focus("end");
    setReady(true);
  }, [editor, bookId, noteId]);

  useEffect(
    () => () => {
      if (timer.current) clearTimeout(timer.current);
    },
    [],
  );

  const handleDone = useCallback(async () => {
    if (timer.current) {
      clearTimeout(timer.current);
      timer.current = null;
    }
    if (editor) await persist(editor);
    void flushNoteSyncNow(); // leaving the editor: write this note to the server now
    onDone();
  }, [editor, persist, onDone]);

  const status = () => {
    if (state === "saving") return <span className="text-text-subtle">Saving…</span>;
    if (state === "saved") {
      return (
        <span className="flex items-center gap-1 text-text-subtle">
          <Check className="h-3 w-3" strokeWidth={1.5} />
          Saved
        </span>
      );
    }
    if (state === "pending") {
      return <span className="text-text-subtle">Unsaved changes</span>;
    }
    return null;
  };

  return (
    <div className={cn("flex min-h-0 flex-1 flex-col", className)}>
      <div className="shrink-0 flex items-center justify-between px-4 py-3 border-b border-border-subtle">
        <button
          onClick={handleDone}
          className="flex items-center gap-1.5 text-body-sm text-text-muted hover:text-text-primary transition-colors"
        >
          <ArrowLeft className="h-3.5 w-3.5" strokeWidth={1.5} />
          Done
        </button>
        <span className="text-body-sm">{status()}</span>
      </div>

      <BlockToolbar editor={editor} onCite={cite} />
      {citing && (
        <p className="shrink-0 px-4 pt-2 text-body-sm text-accent">
          Now select the text in the book to cite it.
        </p>
      )}

      {editor?.isEmpty && (
        <p className="shrink-0 px-4 pt-2 text-body-sm text-text-subtle">
          Tip: "# " starts a heading, "- " starts a bullet — or use the buttons
          above.
        </p>
      )}

      <div className="flex-1 min-h-0 overflow-y-auto overscroll-contain px-4 py-3">
        {!ready ? (
          <div className="flex items-center justify-center py-12">
            <Loader />
          </div>
        ) : (
          <EditorContent editor={editor} />
        )}
      </div>

      {saveError && (
        <div className="shrink-0 flex items-center justify-between gap-2 px-4 py-2 border-t border-border-subtle">
          <p className="text-body-sm text-state-error">{saveError}</p>
          <button
            onClick={() => {
              if (editor) void persist(editor);
            }}
            className="shrink-0 px-2 py-1 rounded text-body-sm text-text-primary hover:bg-bg-elevated transition-colors"
          >
            Try again
          </button>
        </div>
      )}
    </div>
  );
}
