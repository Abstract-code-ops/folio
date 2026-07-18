export type CoverageState = "uncovered" | "mentioned" | "partial" | "well_covered";

// Unchanged from the original component — this is still the per-section
// shape the rest of the app hands to the brain map.
export interface SectionCoverage {
  id: string;
  heading: string;
  chapter_index: number;
  section_index: number | null;
  level: number;
  page_start: number;
  page_end: number;
  word_count: number;
  is_connective: boolean;
  coverage_score: number;
  coverage_state: CoverageState;
  key_terms: string[];
}

// One real, data-bound node per chapter (aggregated from its sections).
export interface ChapterNode {
  chapterIndex: number;
  heading: string;
  pageStart: number;
  pageEnd: number;
  coverageScore: number;
  coverageState: CoverageState;
  sectionIds: string[];
  sectionCount: number;
}

export interface ChapterPosition {
  chapter: ChapterNode;
  x: number;
  y: number;
}
