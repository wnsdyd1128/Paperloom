/**
 * 서재의 저자 검색 (2026-11-25 사용자 요청). 저자는 서재 목록에 들어 있으므로 서버에 묻지 않고 화면에서 찾는다.
 * 검색어의 모든 낱말이 한 저자의 이름에 들어 있어야 그 저자가 맞는다(대소문자 무시, 이름의 어느 자리든:
 * 띄어 쓰지 않는 한글 이름의 뒷부분도 찾는다).
 */
import type { SnippetPart } from "../search/api";
import type { Paper } from "./api";

/** 찾은 저자: 이름을 찾은 낱말로 나눈 조각과, 그 논문의 다른 저자 수 */
export type AuthorHit = Readonly<{ name: readonly SnippetPart[]; others: number }>;

/** 검색어를 낱말로 나눈다. 글자가 없으면 빈 목록이다. */
export function queryWords(query: string): readonly string[] {
  return query.normalize("NFC").toLowerCase().split(/\s+/).filter(Boolean);
}

/** 이름에 모든 낱말이 있으면 찾은 곳을 표시한 조각, 하나라도 없으면 null */
export function markName(name: string, words: readonly string[]): readonly SnippetPart[] | null {
  const text = name.normalize("NFC");
  const lower = text.toLowerCase();
  const ranges: [number, number][] = [];
  for (const word of words) {
    const start = lower.indexOf(word);
    if (start < 0) return null;
    ranges.push([start, start + word.length]);
  }
  // 소문자로 바꾸면 길이가 달라지는 글자가 있으면 자리를 믿을 수 없다: 찾았다고만 하고 표시는 하지 않는다
  if (lower.length !== text.length || ranges.length === 0) return [{ text, match: false }];
  // 겹치거나 맞닿은 자리는 하나로 합쳐 한 번만 표시한다
  ranges.sort((a, b) => a[0] - b[0]);
  const merged: [number, number][] = [];
  for (const [start, end] of ranges) {
    const last = merged.at(-1);
    if (last && start <= last[1]) last[1] = Math.max(last[1], end);
    else merged.push([start, end]);
  }
  const parts: SnippetPart[] = [];
  let at = 0;
  for (const [start, end] of merged) {
    if (start > at) parts.push({ text: text.slice(at, start), match: false });
    parts.push({ text: text.slice(start, end), match: true });
    at = end;
  }
  if (at < text.length) parts.push({ text: text.slice(at), match: false });
  return parts;
}

/** 저자가 맞는 논문 → 처음 맞은 저자(논문의 저자 차례). 검색어에 글자가 없으면 아무것도 찾지 않는다. */
export function searchAuthors(papers: readonly Pick<Paper, "paper_id" | "authors">[], query: string): ReadonlyMap<string, AuthorHit> {
  const words = queryWords(query);
  const hits = new Map<string, AuthorHit>();
  if (words.length === 0) return hits;
  for (const paper of papers) {
    for (const author of paper.authors) {
      const name = markName(author, words);
      if (!name) continue;
      hits.set(paper.paper_id, { name, others: paper.authors.length - 1 });
      break;
    }
  }
  return hits;
}
