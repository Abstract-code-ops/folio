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
  ingestion_status: IngestionStatus;
  section_count: number | null;
  word_count: number | null;
  created_at: string | null;
}

export interface BookListResponse {
  books: BookResponse[];
  total: number;
}
