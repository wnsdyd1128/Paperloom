/**
 * 서재의 태그 거르기 (U6, 시안 Library 태그 메뉴): 고른 태그 가운데 하나라도 / 모두 포함, 또는 태그 없음.
 * 태그 이름은 대소문자를 가리지 않는다(서버도 같다).
 */
export type TagMode = "any" | "all";
export type TagFilter = Readonly<{ tags: readonly string[]; mode: TagMode; untagged: boolean }>;
type Tagged = Readonly<{ tags: readonly string[] }>;

export const NO_TAG_FILTER: TagFilter = { tags: [], mode: "any", untagged: false };

export function matchesTags(paper: Tagged, filter: TagFilter): boolean {
  if (filter.untagged) return paper.tags.length === 0;
  if (filter.tags.length === 0) return true;
  const own = new Set(paper.tags.map((tag) => tag.toLowerCase()));
  const wanted = filter.tags.map((tag) => tag.toLowerCase());
  return filter.mode === "all" ? wanted.every((tag) => own.has(tag)) : wanted.some((tag) => own.has(tag));
}

/** 태그마다 그 태그가 붙은 논문 수, 이름 차례 */
export function tagCounts(papers: readonly Tagged[]): { name: string; count: number }[] {
  const counts = new Map<string, { name: string; count: number }>();
  for (const paper of papers) {
    for (const name of paper.tags) {
      const key = name.toLowerCase();
      const entry = counts.get(key) ?? { name, count: 0 };
      entry.count += 1;
      counts.set(key, entry);
    }
  }
  return [...counts.values()].sort((a, b) => a.name.localeCompare(b.name));
}
