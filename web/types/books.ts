// TypeScript types for Book domain — mirrors FastAPI Pydantic response models

export type IngestionStatus =
  | "not_started"
  | "processing"
  | "completed"
  | "failed";

export interface BookResponse {
  id: string;
  title: string;
  author: string;
  description: string | null;
  cover_image_url: string | null;
  storage_url: string;
  ingestion_status: IngestionStatus;
  section_count: number | null;
  word_count: number | null;
  created_at: string | null;
  /** Present on GET /books/{id}?load_sections=true only. */
  sections?: BookSection[];
}
/** Enough of a section to map a page to it — not the coverage map. */
export interface BookSection {
  id: string;
  heading: string;
  page_start: number;
  page_end: number;
  level: number;
}

export interface BookListResponse {
  books: BookResponse[];
  total: number;
}