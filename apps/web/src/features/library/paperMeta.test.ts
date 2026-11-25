import { describe, expect, it } from "vitest";

import { paperMeta } from "./paperMeta";

const paper = (authors: string[], year: number | null, pages: number) => ({ authors, year, current_version: { page_count: pages } });

describe("paperMeta", () => {
  it("저자 둘까지는 모두 쓰고 연도·쪽 수를 붙인다", () => {
    expect(paperMeta(paper(["Liu", "Layland"], 1973, 16))).toBe("Liu, Layland · 1973 · 16쪽");
    expect(paperMeta(paper(["Lamport"], 1978, 8))).toBe("Lamport · 1978 · 8쪽");
  });

  it("저자가 셋부터면 첫 저자와 나머지 수로 줄인다", () => {
    expect(paperMeta(paper(["Vaswani", "Shazeer", "Parmar"], 2017, 15))).toBe("Vaswani 외 2명 · 2017 · 15쪽");
  });

  it("논문 정보에 없는 값은 빼고 구분점을 남기지 않는다", () => {
    expect(paperMeta(paper([], null, 4))).toBe("4쪽");
    expect(paperMeta(paper([], 2022, 4))).toBe("2022 · 4쪽");
    expect(paperMeta(paper(["Davis", "Burns"], null, 44))).toBe("Davis, Burns · 44쪽");
  });
});
