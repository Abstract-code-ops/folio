// TypeScript types for Chat/Q&A domain — mirrors FastAPI Pydantic response models

export type QaEvent =
  | QaTokenEvent
  | QaCitationEvent
  | QaNotCoveredEvent
  | QaDoneEvent
  | QaErrorEvent;

export interface QaTokenEvent {
  type: "token";
  text: string;
}

export interface QaCitationEvent {
  type: "citation";
  passage: number;
  chunk_index: number;
  section_heading: string;
  page_start: number | null;
  page_end: number | null;
  excerpt: string;
}

export interface QaNotCoveredEvent {
  type: "not_covered";
  text: string;
}

export interface QaDoneEvent {
  type: "done";
  qa_message_id: string;
}

export interface QaErrorEvent {
  type: "error";
  text: string;
}

export interface SummarizeResponse {
  summary: string;
}
