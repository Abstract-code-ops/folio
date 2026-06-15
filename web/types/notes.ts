// TypeScript types for Note Session domain — mirrors FastAPI Pydantic response models

export type NoteSource = "pasted" | "ai_generated";
export type NoteSessionStatus =
  | "pending"
  | "processing"
  | "completed"
  | "failed";

export interface NoteSessionResponse {
  id: string;
  book_id: string;
  title: string | null;
  source: NoteSource;
  status: NoteSessionStatus;
  matched_section_count: number | null;
  job_id: string;
  created_at: string;
}
