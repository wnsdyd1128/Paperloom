import { describe, expect, it } from "vitest";

import { type Spring, spring, springEasing, step, SUBSTEPS, tune } from "./spring";

/** startLoop의 한 화면과 같게 적분한다: 1/60초를 4번 나눠 */
function run(s: Spring, seconds: number) {
  const frames = Math.round(seconds * 60);
  let peak = s.x;
  for (let f = 0; f < frames; f++) {
    for (let i = 0; i < SUBSTEPS; i++) step(s, 1 / 60 / SUBSTEPS);
    peak = Math.max(peak, s.x);
  }
  return peak;
}

describe("spring (원본 Motion Studies 엔진)", () => {
  it("목표로 가서 멈춘다", () => {
    const s = spring(0, 260, 21);
    s.t = 1;
    run(s, 2);
    expect(s.x).toBeCloseTo(1, 3);
    expect(Math.abs(s.v)).toBeLessThan(1e-3);
  });

  it("damping이 낮으면 한 번 넘쳤다 돌아온다 (420/14)", () => {
    const s = spring(0, 420, 14);
    s.t = 1;
    expect(run(s, 1.5)).toBeGreaterThan(1.05);
  });

  it("움직임 줄이기에서는 임계 감쇠라 넘치지 않는다", () => {
    const s = spring(0, 420, 14, true);
    expect(s.c).toBeCloseTo(2 * Math.sqrt(420));
    s.t = 1;
    expect(run(s, 1.5)).toBeLessThanOrEqual(1 + 1e-6);
  });

  it("tune은 같은 spring의 느낌만 바꾼다", () => {
    const s = spring(5, 900, 50);
    tune(s, 280, 22);
    expect(s).toMatchObject({ x: 5, k: 280, c: 22 });
    tune(s, 280, 22, true);
    expect(s.c).toBeCloseTo(2 * Math.sqrt(280));
  });
});

describe("springEasing (같은 곡선을 CSS linear()로)", () => {
  it("0에서 시작해 1로 끝나고, 1/60초 간격 점들이 JS spring과 같다", () => {
    const { easing, duration } = springEasing(340, 26);
    const points = easing.slice("linear(".length, -1).split(", ").map(Number);
    expect(points[0]).toBe(0);
    expect(points.at(-1)).toBe(1);
    expect(duration).toBeCloseTo((points.length - 1) / 60);
    const s = spring(0, 340, 26);
    s.t = 1;
    for (let i = 1; i < 6; i++) {
      run(s, 1 / 60);
      expect(points[i]).toBeCloseTo(s.x, 3);
    }
  });

  it("넘치는 spring은 1을 넘는 점을 남긴다 (말풍선 300/22)", () => {
    const points = springEasing(300, 22).easing.slice("linear(".length, -1).split(", ").map(Number);
    expect(Math.max(...points)).toBeGreaterThan(1);
  });
});
