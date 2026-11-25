/** 서재 표에서 제목 아래에 놓는 한 줄: 저자 · 연도 · 쪽 수. 논문 정보에 없는 값은 뺀다(쪽 수는 늘 있다). */
import type { Paper } from "./api";

type MetaSource = Readonly<{ authors: Paper["authors"]; year: Paper["year"]; current_version: Readonly<{ page_count: number }> }>;

/** 저자가 셋부터면 "첫 저자 외 n명"으로 줄인다. */
export function paperMeta(paper: MetaSource): string {
  const { authors, year } = paper;
  const names = authors.length > 2 ? `${authors[0]} 외 ${authors.length - 1}명` : authors.join(", ");
  return [names, year, `${paper.current_version.page_count}쪽`].filter(Boolean).join(" · ");
}
