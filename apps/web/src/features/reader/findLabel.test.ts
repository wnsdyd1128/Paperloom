import { describe, expect, it } from "vitest";

import { findLabel } from "./FindBar";

describe("findLabel", () => {
  it("찾는 말이 없으면 비어 있다", () => {
    expect(findLabel("", { current: 0, total: 0 }, false)).toBe("");
    expect(findLabel("   ", { current: 2, total: 5 }, false)).toBe("");
  });

  it("찾는 중·없음·몇 번째", () => {
    expect(findLabel("cache", { current: 0, total: 0 }, true)).toBe("찾는 중…");
    expect(findLabel("cache", { current: 0, total: 0 }, false)).toBe("없음");
    expect(findLabel("cache", { current: 3, total: 12 }, false)).toBe("3 / 12");
    expect(findLabel("cache", { current: 0, total: 5 }, true)).toBe("– / 5");
  });
});
