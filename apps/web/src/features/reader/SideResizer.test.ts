import { describe, expect, it } from "vitest";

import { clampSideWidth, SIDE_WIDTH } from "./SideResizer";

describe("clampSideWidth", () => {
  it("최소·최대 사이로 맞추고, 본문 자리(MIN_STAGE)를 남긴다 (2026-10-02 사용자 요청: 대화창 너비 조절)", () => {
    expect(clampSideWidth(500, 1920)).toBe(500);
    expect(clampSideWidth(100, 1920)).toBe(SIDE_WIDTH.min);
    expect(clampSideWidth(5000, 1920)).toBe(SIDE_WIDTH.max);
    expect(clampSideWidth(900, 1200)).toBe(1200 - SIDE_WIDTH.minStage); // 좁은 창에서는 본문 자리를 남긴다
    expect(clampSideWidth(900, 500)).toBe(SIDE_WIDTH.min); // 아주 좁아도 최소 너비는 둔다
    expect(clampSideWidth(433.6, 1920)).toBe(434);
  });
});
