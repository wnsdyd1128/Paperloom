import { describe, expect, it } from "vitest";

import { dragOffset } from "./drag";

describe("dragOffset", () => {
  const base = { left: 100, top: 400 };
  const bounds = { width: 1000, grip: 120 };

  it("끈 만큼 옮긴다", () => {
    expect(dragOffset(base, { x: 0, y: 0 }, { x: 50, y: -30 }, bounds)).toEqual({ x: 50, y: -30 });
    expect(dragOffset(base, { x: 20, y: 10 }, { x: 5, y: 5 }, bounds)).toEqual({ x: 25, y: 15 });
  });

  it("스크롤 내용의 왼쪽·위 밖으로는 나가지 않는다", () => {
    expect(dragOffset(base, { x: 0, y: 0 }, { x: -500, y: -900 }, bounds)).toEqual({ x: -100, y: -400 });
  });

  it("오른쪽으로 나가도 머리의 잡을 곳(grip)은 남는다", () => {
    expect(dragOffset(base, { x: 0, y: 0 }, { x: 5000, y: 0 }, bounds)).toEqual({ x: 1000 - 120 - 100, y: 0 });
  });
});
