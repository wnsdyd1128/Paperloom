import { describe, expect, it } from "vitest";

import { figureAt, type PageFigure } from "./figures";

const figure = (u0: number, v0: number, u1: number, v1: number, source = "image"): PageFigure => ({
  box: { u0, v0, u1, v1 },
  source,
});

describe("figureAt", () => {
  const outer = figure(0.1, 0.1, 0.9, 0.5, "vector");
  const inner = figure(0.2, 0.2, 0.4, 0.3);

  it("점을 담은 후보 중 가장 작은(안쪽) 그림을 고른다", () => {
    expect(figureAt([outer, inner], 0.3, 0.25)).toBe(inner);
    expect(figureAt([outer, inner], 0.8, 0.4)).toBe(outer);
  });

  it("경계도 그림 안이고, 밖이면 null", () => {
    expect(figureAt([inner], 0.2, 0.2)).toBe(inner);
    expect(figureAt([inner], 0.41, 0.25)).toBeNull();
    expect(figureAt([], 0.5, 0.5)).toBeNull();
  });
});
