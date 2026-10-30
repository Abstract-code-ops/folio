import { create } from "zustand";
import type { LocalLink } from "./notes-store";

/**
 * Coordinates a "cite this" request between the note editor (which owns the
 * note) and the reader (which owns the PDF selection and the section map).
 *
 * The editor posts a request; the reader, on the next text selection, resolves
 * the page→section and posts back a ready-to-attach link.
 */
export interface CiteRequest {
  noteId: string;
  /** The block the citation attaches to; `null` means append a new block. */
  blockId: string | null;
  /** The note-side text the student selected to cite. */
  quote: string | null;
}

export interface ResolvedLink {
  noteId: string;
  blockId: string | null;
  link: LocalLink;
}

interface CiteBridgeState {
  citeRequest: CiteRequest | null;
  resolvedLink: ResolvedLink | null;
  setCiteRequest: (request: CiteRequest | null) => void;
  setResolvedLink: (resolved: ResolvedLink | null) => void;
}

export const useCiteBridge = create<CiteBridgeState>((set) => ({
  citeRequest: null,
  resolvedLink: null,
  setCiteRequest: (request) => set({ citeRequest: request }),
  setResolvedLink: (resolved) => set({ resolvedLink: resolved }),
}));
