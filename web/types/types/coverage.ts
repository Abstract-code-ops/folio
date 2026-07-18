// TypeScript types for Coverage domain — mirrors FastAPI Pydantic response models

export type CoverageState =
  | "uncovered"
  | "mentioned"
  | "partial"
  | "well_covered";

export interface SectionCoverage {
  id: string;
  book_id: string;
  parent_section_id: string | null;
  chapter_index: number;
  section_index: number | null;
  level: number;
  heading: string;
  page_start: number;
  page_end: number;
  word_count: number;
  is_connective: boolean;
  coverage_score: number;
  coverage_state: CoverageState;
  key_terms: string[];
}

export interface CoverageMapResponse {
  book_id: string;
  sections: SectionCoverage[];
}
