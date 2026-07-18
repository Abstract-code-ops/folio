// Collapses per-section coverage data into one node per chapter, so the
// map shows a readable number of nodes instead of one per section.

import type { SectionCoverage, ChapterNode, CoverageState } from "./types";

const STATE_RANK: Record<CoverageState, number> = {
  uncovered: 0,
  mentioned: 1,
  partial: 2,
  well_covered: 3,
};

export function aggregateSectionsToChapters(sections: SectionCoverage[]): ChapterNode[] {
  const byChapter = new Map<number, SectionCoverage[]>();
  for (const s of sections) {
    const bucket = byChapter.get(s.chapter_index);
    if (bucket) bucket.push(s);
    else byChapter.set(s.chapter_index, [s]);
  }

  const chapters: ChapterNode[] = Array.from(byChapter.entries())
    .sort(([a], [b]) => a - b)
    .map(([chapterIndex, secs]) => {
      const pageStart = Math.min(...secs.map((s) => s.page_start));
      const pageEnd = Math.max(...secs.map((s) => s.page_end));
      const avgScore = secs.reduce((sum, s) => sum + s.coverage_score, 0) / secs.length;

      // Majority vote on coverage_state; ties favor the higher state so a
      // chapter isn't shown as weaker than most of its sections actually are.
      const counts = new Map<CoverageState, number>();
      for (const s of secs) counts.set(s.coverage_state, (counts.get(s.coverage_state) ?? 0) + 1);
      let state: CoverageState = "uncovered";
      let bestCount = -1;
      counts.forEach((count, candidate) => {
        if (count > bestCount || (count === bestCount && STATE_RANK[candidate] > STATE_RANK[state])) {
          state = candidate;
          bestCount = count;
        }
      });

      // Chapter heading: the section marked as the chapter title
      // (section_index === null) if present, else the earliest section by page.
      const sortedByPage = [...secs].sort((a, b) => a.page_start - b.page_start);
      const titleSection = secs.find((s) => s.section_index === null) ?? sortedByPage[0];

      const chapter: ChapterNode = {
        chapterIndex,
        heading: titleSection?.heading ?? `Chapter ${chapterIndex + 1}`,
        pageStart,
        pageEnd,
        coverageScore: Math.round(avgScore * 10) / 10,
        coverageState: state,
        sectionIds: secs.map((s) => s.id),
        sectionCount: secs.length,
      };
      return chapter;
    });

  return chapters;
}
