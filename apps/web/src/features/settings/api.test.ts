import { describe, expect, it } from "vitest";

import { approxPages } from "./api";

describe("approxPages (논문 본문 한도의 쪽 수 어림)", () => {
  it("한 단 논문 쪽당 약 3,000자로 어림한다", () => {
    expect([12_000, 40_000, 120_000, 300_000].map(approxPages)).toEqual([4, 13, 40, 100]);
  });
});
