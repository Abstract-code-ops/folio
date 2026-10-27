// TypeScript types for the eval page — mirrors FastAPI QaTurnResponse.

export interface RetrievedPassage {
  role: "match" | "context";
  heading: string;
  breadcrumb: string;
  page_start: number | null;
  page_end: number | null;
  chunk_index: number | null;
  distance: number | null;
}

export interface TurnDiagnostics {
  mode: "agent" | "legacy";
  action: "searched_book" | "answered_without_retrieval" | "retrieved";
  queries: string[];
  retrieved: RetrievedPassage[];
  citations: number;
  answer_chars: number;
  error: string | null;
}

export interface CitationSource {
  passage: number;
  section_heading: string;
  page_start: number | null;
  page_end: number | null;
  excerpt: string;
}

export interface QaTurn {
  id: string;
  created_at: string;
  book_id: string;
  book_title: string | null;
  question: string;
  answer: string;
  section_id: string | null;
  sources: CitationSource[] | null;
  diagnostics: TurnDiagnostics | null;
}

export interface QaTurnListResponse {
  turns: QaTurn[];
  total: number;
}
