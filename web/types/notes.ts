// TypeScript types for Note Session domain — mirrors FastAPI Pydantic response models

export type NoteSource = "pasted" | "ai_generated";
export type NoteSessionStatus =
  | "pending"
  | "processing"
  | "completed"
  | "failed";

export interface NoteSessionListResponse {
  sessions: NoteSessionResponse[];
  total: number;
}

export interface NoteSessionResponse {
  id: string;
  book_id: string;
  title: string | null;
  source: NoteSource;
  status: NoteSessionStatus;
  matched_section_count: number | null;
  /** Present only on the reply to a create request; null for a stored session. */
  job_id: string | null;
  created_at: string;
  /** Sections this note cites, so the panel can find backlinks locally. */
  section_ids: string[];
}

// ── AI-generated notes ────────────────────────────────────────

export interface GeneratedConcept {
  name: string;
  definition: string;
  explanation: string;
  example: string;
  self_check: string;
}

export interface GeneratedSectionNotes {
  section_id: string;
  section_heading: string;
  page_start: number;
  page_end: number;
  concepts: GeneratedConcept[];
}

// ── Note documents: blocks and links ──────────────────────────

export type BlockKind = "heading" | "paragraph" | "bullet" | "card";
export type BlockOrigin = "typed" | "ai" | "ocr";
export type LinkStatus = "suggested" | "accepted" | "dismissed";export type LinkOrigin = "generated" | "auto" | "manual";

/** A stored link: what a citation chip renders and where it jumps to. */
export interface NoteLink {
  id: string;
  section_id: string | null;
  anchor_heading_path: string;
  page_start: number;
  page_end: number;
  excerpt: string;
  status: LinkStatus;
  origin: LinkOrigin;
}

export interface NoteBlock {
  id: string;
  position: number;
  kind: BlockKind;
  text: string;
  origin: BlockOrigin;
  links: NoteLink[];
}

/** A whole note: its header plus its blocks in order. */
export interface NoteDetail {
  id: string;
  book_id: string;
  title: string | null;
  source: NoteSource;
  status: NoteSessionStatus;
  matched_section_count: number | null;
  created_at: string;
  updated_at: string | null;
  /** Notes that predate blocks keep their text here. */
  raw_text: string;
  blocks: NoteBlock[];
}

/** A link as submitted — the server derives the excerpt hash itself. */
export interface NoteLinkDraft {
  section_id?: string | null;
  anchor_heading_path: string;
  page_start: number;
  page_end: number;
  excerpt: string;
  origin: LinkOrigin;
  status?: LinkStatus;
}

/**
 * A block as submitted. `id` is present for a block that already exists, which
 * is how autosave keeps its links; omit it for a block the editor just made.
 */
export interface NoteBlockDraft {
  id?: string;
  kind: BlockKind;
  text: string;
  origin?: BlockOrigin;
  links?: NoteLinkDraft[];
}

/** A link as the local store flushes it to the server (client id, no server-only fields). */
export interface NoteBatchLink {
  id: string;
  section_id: string | null;
  anchor_heading_path: string;
  page_start: number;
  page_end: number;
  excerpt: string;
  status: LinkStatus;
  origin: LinkOrigin;
}

export interface NoteBatchBlock {
  id: string;
  kind: BlockKind;
  text: string;
  origin: BlockOrigin;
  links: NoteBatchLink[];
}

/** One note's full current state, as flushed by the local-first sync engine. */
export interface NoteBatchNote {
  id: string;
  book_id: string;
  title: string | null;
  source: NoteSource;
  blocks: NoteBatchBlock[];
}

export interface UpsertNotesBatchResponse {
  synced: { id: string; updated_at: string }[];
}

/** Events streamed while a note is generated from a topic. */
export type NoteTopicEvent =
  | {
      type: "card";
      index: number;
      concept: string;
      definition: string;
      explanation: string;
      example: string;
      sources: number[];
    }
  | { type: "gaps"; gaps: string[] }
  | {
      type: "done";
      title: string;
      sections: number;
      blocks: {
        kind: BlockKind;
        text: string;
        origin: BlockOrigin;
        links: {
          section_id: string | null;
          anchor_heading_path: string;
          page_start: number;
          page_end: number;
          excerpt: string;
          status: LinkStatus;
          origin: LinkOrigin;
        }[];
      }[];
    }
  | { type: "not_covered"; message: string }
  | { type: "error"; message: string };