"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { Editor } from "@tiptap/core";
import { EditorContent, useEditor } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import { Placeholder } from "@tiptap/extension-placeholder";
import { AlertCircle, ArrowLeft, Check } from "lucide-react";
import { cn } from "@/lib/utils";
import { apiClient } from "@/lib/api-client";
import { Loader } from "@/components/ui/loader";
import type { NoteDetail } from "@/types/notes";
import { BlockBulletList, BlockHeading, BlockParagraph } from "./editor/block-id";
import { BlockToolbar } from "./editor/BlockToolbar";
import { blocksToContent, docToBlocks } from "./editor/doc-blocks";

/** Quiet time before an autosave. Long enough to finish a sentence. */
const AUTOSAVE_DELAY_MS = 2000;

export interface NoteEditorProps {
  noteId: string;
  /** Leave the editor; the read view reloads the note. */
  onDone: () => void;
  /** Called after a successful save, so a parent can refresh a list. */
  onSaved?: (note: NoteDetail) => void;
  className?: string;
}

type SaveState = "idle" | "pending" | "saving" | "saved" | "error";

export function NoteEditor({
  noteId,
  onDone,
  onSaved,
  className,
}: NoteEditorProps) {
  const [note, setNote] = useState<NoteDetail | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [state, setState] = useState<SaveState>("idle");
  const [saveError, setSaveError] = useState<string | null>(null);

  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const saveSeq = useRef(0);
  const dirty = useRef(false);
  const loaded = useRef(false);

  const extensions = useMemo(
    () => [
      // Only the nodes a note can hold: paragraphs, headings and one-level
      // bullets. Lists of lists, quotes and code blocks are noise in study
      // notes, and each one is another shape the block mapper must handle.
      StarterKit.configure({
        paragraph: false,
        heading: false,
        bulletList: false,
        orderedList: false,
        blockquote: false,
        codeBlock: false,
        horizontalRule: false,
        link: false,
        underline: false,
      }),
      BlockParagraph,
      BlockHeading.configure({ levels: [3] }),
      BlockBulletList,
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
        const saved = await apiClient.saveNoteBlocks(
          noteId,
          docToBlocks(editor.getJSON()),
        );
        // A newer save may already have started; its result is the truth.
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
    [noteId, onSaved],
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
    // Required under the Next.js server renderer: laying out ProseMirror on the
    // server produces markup the client immediately disagrees with.
    immediatelyRender: false,
    // The toolbar reads isActive()/isEmpty(), which only update if the panel
    // re-renders per transaction. Cheap at note size, and without it the active
    // block type would be wrong after the first click.
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

  // Load once, without emitting an update -- otherwise setting the initial
  // content would look like an edit and immediately save over the note.
  useEffect(() => {
    if (!editor || loaded.current || !note) return;
    loaded.current = true;

    // A note written before blocks existed keeps its text in raw_text. Seed the
    // editor from it rather than showing an empty page; the first save converts
    // it into blocks, which is the migration path.
    const content =
      note.blocks.length > 0
        ? blocksToContent(note.blocks)
        : note.raw_text
            .split(/\n{2,}/)
            .filter((paragraph) => paragraph.trim())
            .map((paragraph) => ({
              type: "paragraph",
              content: [{ type: "text", text: paragraph }],
            }));

    editor.commands.setContent(
      {
        type: "doc",
        content: content.length > 0 ? content : [{ type: "paragraph" }],
      },
      { emitUpdate: false },
    );
    editor.commands.focus("end");
  }, [editor, note]);

  const loadNote = useCallback(async () => {
    setLoadError(null);
    try {
      setNote(await apiClient.getNote(noteId));
    } catch (err) {
      setLoadError(
        err instanceof Error ? err.message : "Couldn't open this note",
      );
    }
  }, [noteId]);

  useEffect(() => {
    loadNote();
  }, [loadNote]);

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
    // Never leave silently: a pending keystroke is saved before we leave.
    if (editor) await persist(editor);
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
    <div className={cn("flex flex-col h-full", className)}>
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

      <BlockToolbar editor={editor} />

      {editor?.isEmpty && (
        <p className="shrink-0 px-4 pt-2 text-body-sm text-text-subtle">
          Tip: "# " starts a heading, "- " starts a bullet — or use the buttons
          above.
        </p>
      )}

      <div className="flex-1 overflow-y-auto px-4 py-3">
        {loadError ? (
          <div className="flex flex-col items-center justify-center py-12 text-center">
            <AlertCircle className="h-8 w-8 text-text-subtle mb-3" />
            <p className="text-body-sm text-state-error mb-3">{loadError}</p>
            <button
              onClick={loadNote}
              className="px-3 py-1.5 rounded-md bg-bg-elevated text-body-sm text-text-primary hover:bg-bg-surface transition-colors"
            >
              Try again
            </button>
          </div>
        ) : !note ? (
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
