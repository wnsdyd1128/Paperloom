import { describe, expect, it } from "vitest";

import { pageRanges } from "./pageRanges";

describe("pageRanges", () => {
  it("보낸 쪽들을 이어지는 묶음으로 적는다 (2026-10-02 사용자 확인: \"p.1–29\"가 전문을 보낸 것처럼 보였다)", () => {
    expect(pageRanges([3, 4, 5, 27, 28, 29])).toBe("p.3–5, 27–29");
    expect(pageRanges([5, 3, 4, 4])).toBe("p.3–5");
    expect(pageRanges([7])).toBe("p.7");
    expect(pageRanges([1, 3, 4])).toBe("p.1, 3–4");
    expect(pageRanges([])).toBe("");
  });
});
