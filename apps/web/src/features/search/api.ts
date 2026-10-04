/** 논문 제목 검색 REST 클라이언트 (backend/src/paperloom/retrieval/routes.py, IMPL §7.1). */

import { parseJson } from "../../shared/http";

/** 제목 조각. match는 검색어와 일치한 부분이다. HTML이 아니라 글자로 그린다. */
export type SnippetPart = Readonly<{ text: string; match: boolean }>;

export type PaperHit = Readonly<{ paper_id: string; version_id: string; title: readonly SnippetPart[] }>;

export type SearchResult = Readonly<{ query: string; papers: readonly PaperHit[] }>;

export async function search(query: string): Promise<SearchResult> {
  return parseJson<SearchResult>(await fetch(`/api/v1/search?${new URLSearchParams({ q: query })}`));
}
