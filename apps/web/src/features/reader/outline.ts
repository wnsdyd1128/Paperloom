/**
 * 목차 패널의 항목 (U4, IMPL §10.8): PDF 목차(outline)가 있으면 그것을, 없으면 본문 제목(서버 documents.headings,
 * 2026-10-02 사용자 결정 D6)을 쓴다. PDF 목차는 목적지(쪽 참조·/XYZ 등)로, 본문 제목은 그 줄 상자로 간다.
 */
import type { PDFDocumentProxy } from "pdfjs-dist";

import type { Heading } from "../library/api";

export type TocTarget =
  | Readonly<{ kind: "dest"; dest: readonly unknown[] }> // PDF 목적지 배열 (scrollPageIntoView의 destArray)
  | Readonly<{ kind: "box"; box: readonly number[] }>; // 본문 제목 줄의 정본 좌표

/**
 * 목차 항목. box는 그 항목이 가리키는 쪽 안 자리(정본 좌표 [u0, v0, u1, v1]): 본문 제목은 그 줄 상자, PDF 목적지는 그 점.
 * 지금 항목(읽는 줄 위의 마지막 항목)을 고를 때 쓴다.
 */
export type TocEntry = Readonly<{ title: string; level: number; pageIndex: number; box: readonly number[]; target: TocTarget }>;

/** 읽는 줄(스크롤 영역 위쪽 3분의 1)이 걸친 쪽과, 그 쪽의 항목이 읽는 줄 위에 있는지 */
export type ReadingLine = Readonly<{ pageIndex: number; above: (entry: TocEntry) => boolean }>;

type OutlineItem = Readonly<{ title: string; dest: unknown; items: readonly OutlineItem[] }>;
type Resolve = (dest: unknown) => Promise<Readonly<{ pageIndex: number; dest: readonly unknown[]; box: readonly number[] }> | null>;

/** PDF.js getOutline 결과를 차례대로 펼친다. 목적지를 풀지 못한 항목(바깥 링크 등)은 빼고 아래 항목은 남긴다. */
export async function flattenOutline(items: readonly OutlineItem[] | null, resolve: Resolve, level = 1): Promise<TocEntry[]> {
  const entries: TocEntry[] = [];
  for (const item of items ?? []) {
    const resolved = await resolve(item.dest);
    if (resolved) {
      const title = item.title.replace(/\s+/g, " ").trim();
      entries.push({ title, level, pageIndex: resolved.pageIndex, box: resolved.box, target: { kind: "dest", dest: resolved.dest } });
    }
    entries.push(...(await flattenOutline(item.items, resolve, level + 1)));
  }
  return entries;
}

/** 이름 있는 목적지·쪽 참조를 쪽 번호(0부터)·목적지 배열·가리키는 점으로 푼다. 풀지 못하면 null. */
export function pdfResolver(pdf: PDFDocumentProxy): Resolve {
  return async (dest) => {
    try {
      const explicit = typeof dest === "string" ? await pdf.getDestination(dest) : dest;
      if (!Array.isArray(explicit) || explicit.length === 0) return null;
      const [ref] = explicit;
      const pageIndex = typeof ref === "number" ? ref : ref && typeof ref === "object" ? await pdf.getPageIndex(ref) : null;
      if (pageIndex === null) return null;
      const [u, v] = destPoint(explicit, (await pdf.getPage(pageIndex + 1)).view);
      return { pageIndex, dest: explicit, box: [u, v, u, v] };
    } catch {
      return null; // 깨진 목적지는 그 항목만 뺀다
    }
  };
}

/**
 * PDF 목적지 배열(`[쪽, {name}, …]`, PDF 32000 12.3.2.2)이 가리키는 쪽 안 자리를 정규화 [u, v]로(v는 아래로 커진다).
 * view는 그 쪽의 상자 [x0, y0, x1, y1](PDF 좌표, 위로 커진다). 위치가 없는 목적지(Fit, null)는 쪽 맨 위·왼쪽이다.
 */
export function destPoint(dest: readonly unknown[], view: readonly number[]): [number, number] {
  const [x0, y0, x1, y1] = view;
  const kind = (dest[1] as { name?: string } | null)?.name;
  const at = (index: number) => (typeof dest[index] === "number" ? (dest[index] as number) : null);
  const [left, top] =
    kind === "XYZ" ? [at(2), at(3)] : kind === "FitH" || kind === "FitBH" ? [null, at(2)] : kind === "FitR" ? [at(2), at(5)] : [null, null];
  const clamp = (value: number) => Math.min(1, Math.max(0, value));
  return [left === null ? 0 : clamp((left - x0) / (x1 - x0)), top === null ? 0 : clamp((y1 - top) / (y1 - y0))];
}

export function headingEntries(headings: readonly Heading[]): TocEntry[] {
  return headings.map((heading) => ({
    title: heading.title,
    level: heading.level,
    pageIndex: heading.page_index,
    box: heading.box,
    target: { kind: "box", box: heading.box },
  }));
}

/**
 * 지금 항목: 지금 쪽까지 나온 마지막 항목. 첫 항목보다 앞이면 -1.
 * above(항목)는 지금 쪽의 항목이 읽는 줄(스크롤 영역 위쪽 3분의 1, 목차로 간 제목이 오는 줄) 위에 있는지다. 주면 지금 쪽에서는
 * 그 위의 항목만 본다(2026-10-03 사용자 확인: 한 쪽에 5.2와 5.2.1이 있으면 5.2를 눌러도 5.2.1이 강조됐다). 없으면 쪽 단위로만
 * 보아 같은 쪽이면 뒤의 것이다.
 */
export function currentEntry(entries: readonly TocEntry[], pageIndex: number, above?: (entry: TocEntry) => boolean): number {
  let current = -1;
  entries.forEach((entry, index) => {
    const passed = entry.pageIndex < pageIndex || (entry.pageIndex === pageIndex && (above?.(entry) ?? true));
    if (passed && (current < 0 || entry.pageIndex >= entries[current].pageIndex)) current = index;
  });
  return current;
}
