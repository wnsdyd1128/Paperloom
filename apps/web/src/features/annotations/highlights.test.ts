import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Annotation } from "./api";
import { filterHighlights, highlightsMarkdown, rememberHighlightColor, storedHighlightColor } from "./highlights";

const item = (id: string, color: Annotation["color"], quote: string, comment = "", display: string | null = null, kind = "text"): Annotation =>
  ({
    annotation_id: id,
    comment,
    color,
    revision: 1,
    created_at: "2026-10-02T00:00:00Z",
    updated_at: "2026-10-02T00:00:00Z",
    anchor: { anchor_id: `a-${id}`, kind, page_index: Number(id), quote, display_quote: display, quads: [[0, 0, 1, 0, 1, 1, 0, 1]] },
  }) as unknown as Annotation;

describe("filterHighlights", () => {
  const items = [
    item("1", "c1", "Cache delay analysis"),
    item("2", "c2", "f j k", "DBF 정의", "f^j_k"),
    item("3", null, "memo only", "메모 주석"),
    item("4", "c3", "Shared caches"),
  ];

  it("색이 있는 주석만, 고른 색만 보인다", () => {
    expect(filterHighlights(items, new Set(["c1", "c2", "c3"]), "").map((h) => h.annotation_id)).toEqual(["1", "2", "4"]);
    expect(filterHighlights(items, new Set(["c2", "c3"]), "").map((h) => h.annotation_id)).toEqual(["2", "4"]);
    expect(filterHighlights(items, new Set(), "")).toEqual([]);
  });

  it("인용·추정 표기·메모에서 대소문자 없이 찾는다", () => {
    const all = new Set(["c1", "c2", "c3"] as const);
    expect(filterHighlights(items, all, " CACHE ").map((h) => h.annotation_id)).toEqual(["1", "4"]);
    expect(filterHighlights(items, all, "f^j").map((h) => h.annotation_id)).toEqual(["2"]);
    expect(filterHighlights(items, all, "dbf").map((h) => h.annotation_id)).toEqual(["2"]);
    expect(filterHighlights(items, all, "메모 주석")).toEqual([]);
  });
});

describe("highlightsMarkdown", () => {
  it("쪽·인용(추정 표기가 있으면 그것)·메모를 Markdown 목록으로, 추정 표기의 수식은 설정의 구분 기호로", () => {
    const items = [item("1", "c1", "Cache delay analysis"), item("2", "c2", "f j k", "DBF 정의", "f^j_k")];
    expect(highlightsMarkdown(items, "dollar")).toBe("- p.2 “Cache delay analysis”\n- p.3 “$f^j_k$” — DBF 정의");
    expect(highlightsMarkdown(items, "bracket")).toBe("- p.2 “Cache delay analysis”\n- p.3 “\\(f^j_k\\)” — DBF 정의");
    expect(highlightsMarkdown(items, "none")).toBe("- p.2 “Cache delay analysis”\n- p.3 “f^j_k” — DBF 정의");
  });
});

describe("storedHighlightColor", () => {
  beforeEach(() => {
    const values = new Map<string, string>();
    vi.stubGlobal("localStorage", { getItem: (key: string) => values.get(key) ?? null, setItem: (key: string, value: string) => values.set(key, value) });
  });
  afterEach(() => vi.unstubAllGlobals());

  it("처음은 c1, 고른 색을 기억하고 모르는 값은 무시한다", () => {
    expect(storedHighlightColor()).toBe("c1");
    rememberHighlightColor("c3");
    expect(storedHighlightColor()).toBe("c3");
    localStorage.setItem("paperloom.reader.highlightColor", "red");
    expect(storedHighlightColor()).toBe("c1");
  });
});
