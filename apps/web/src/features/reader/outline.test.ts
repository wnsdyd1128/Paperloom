import { describe, expect, it } from "vitest";

import { currentEntry, destPoint, flattenOutline, headingEntries, type TocEntry } from "./outline";

type Item = { title: string; dest: string | null; items: Item[] };
const item = (title: string, dest: string | null, items: Item[] = []): Item => ({ title, dest, items });

describe("flattenOutline", () => {
  const pages: Record<string, number> = { a: 0, b: 1, c: 2 };
  const resolve = async (dest: unknown) =>
    typeof dest === "string" && dest in pages ? { pageIndex: pages[dest], dest: [dest], box: [0, 0.5, 0, 0.5] } : null;

  it("차례대로 펼치고 단계를 매긴다. 풀지 못한 항목(바깥 링크 등)은 빼고 아래 항목은 남긴다", async () => {
    const outline = [item(" 1  Intro\n", "a"), item("2 Method", "b", [item("2.1 Setup", "c")]), item("Web site", null, [item("Child", "a")])];
    expect(await flattenOutline(outline, resolve)).toEqual([
      { title: "1 Intro", level: 1, pageIndex: 0, box: [0, 0.5, 0, 0.5], target: { kind: "dest", dest: ["a"] } },
      { title: "2 Method", level: 1, pageIndex: 1, box: [0, 0.5, 0, 0.5], target: { kind: "dest", dest: ["b"] } },
      { title: "2.1 Setup", level: 2, pageIndex: 2, box: [0, 0.5, 0, 0.5], target: { kind: "dest", dest: ["c"] } },
      { title: "Child", level: 2, pageIndex: 0, box: [0, 0.5, 0, 0.5], target: { kind: "dest", dest: ["a"] } },
    ]);
  });

  it("목차가 없으면 빈 목록", async () => {
    expect(await flattenOutline(null, resolve)).toEqual([]);
    expect(await flattenOutline([], resolve)).toEqual([]);
  });
});

describe("headingEntries", () => {
  it("본문 제목은 그 줄 상자로 간다", () => {
    expect(headingEntries([{ title: "2 Method", page_index: 1, level: 1, block_id: "b", box: [0.1, 0.2, 0.5, 0.22] }])).toEqual([
      { title: "2 Method", level: 1, pageIndex: 1, box: [0.1, 0.2, 0.5, 0.22], target: { kind: "box", box: [0.1, 0.2, 0.5, 0.22] } },
    ]);
  });
});

describe("destPoint (PDF 목적지가 가리키는 쪽 안 자리, 정규화 u·v)", () => {
  const view = [0, 0, 612, 792]; // US Letter, 아래에서 위로 커지는 PDF 좌표
  const ref = { num: 1, gen: 0 };

  it("XYZ는 왼쪽·위, FitH·FitBH는 위, FitR은 왼쪽·위 모서리", () => {
    expect(destPoint([ref, { name: "XYZ" }, 61.2, 396, null], view)).toEqual([0.1, 0.5]);
    expect(destPoint([ref, { name: "FitH" }, 594], view)).toEqual([0, 0.25]);
    expect(destPoint([ref, { name: "FitBH" }, 594], view)).toEqual([0, 0.25]);
    expect(destPoint([ref, { name: "FitR" }, 61.2, 100, 300, 594], view)).toEqual([0.1, 0.25]);
  });

  it("위치가 없으면(Fit, XYZ의 null) 쪽 맨 위, 쪽 밖이면 쪽 끝으로", () => {
    expect(destPoint([ref, { name: "Fit" }], view)).toEqual([0, 0]);
    expect(destPoint([ref, { name: "XYZ" }, null, null, 0], view)).toEqual([0, 0]);
    expect(destPoint([ref, { name: "XYZ" }, -10, 900, 0], view)).toEqual([0, 0]);
    expect(destPoint([ref, { name: "XYZ" }, 700, -5, 0], [0, 0, 612, 792])).toEqual([1, 1]);
  });

  it("쪽 상자가 원점에 있지 않아도", () => {
    expect(destPoint([ref, { name: "XYZ" }, 110, 450, null], [50, 50, 650, 850])).toEqual([0.1, 0.5]);
  });
});

describe("currentEntry", () => {
  const at = (pageIndex: number): TocEntry => ({ title: `p${pageIndex}`, level: 1, pageIndex, box: [0, 0, 1, 1], target: { kind: "box", box: [0, 0, 1, 1] } });
  const entries = [at(0), at(1), at(1), at(3)];

  it("지금 쪽까지 나온 마지막 항목이다(같은 쪽이면 뒤의 것)", () => {
    expect(currentEntry(entries, 0)).toBe(0);
    expect(currentEntry(entries, 1)).toBe(2);
    expect(currentEntry(entries, 2)).toBe(2);
    expect(currentEntry(entries, 9)).toBe(3);
  });

  it("쪽 안 위치를 알면 같은 쪽에서는 읽는 줄 위에 있는 마지막 항목이다 (5.2를 눌렀는데 5.2.1이 강조되던 것)", () => {
    const [first, second] = [entries[1], entries[2]];
    expect(currentEntry(entries, 1, (entry) => entry === first)).toBe(1);
    expect(currentEntry(entries, 1, () => true)).toBe(2);
    // 그 쪽의 항목이 모두 읽는 줄 아래면 앞 쪽의 항목
    expect(currentEntry(entries, 1, () => false)).toBe(0);
    // 다른 쪽 항목은 위치를 보지 않는다
    expect(currentEntry(entries, 2, (entry) => entry !== first && entry !== second)).toBe(2);
  });

  it("첫 항목보다 앞 쪽이거나 목차가 없으면 -1", () => {
    expect(currentEntry([at(2)], 0)).toBe(-1);
    expect(currentEntry([], 0)).toBe(-1);
  });
});
