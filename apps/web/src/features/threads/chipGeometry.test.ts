import { describe, expect, it } from "vitest";

import { leaderLine, toPageUnits, toPixels } from "./chipGeometry";

describe("칩 옮김 (2026-10-02 사용자 요청: 본문 옆 칩을 끌어 옮기고 어느 위치인지 보인다)", () => {
  it("옮긴 만큼을 쪽 너비 비율로 기억해 확대·축소해도 같은 자리다", () => {
    const remembered = toPageUnits({ x: -150, y: 60 }, 600);
    expect(remembered).toEqual({ x: -0.25, y: 0.1 });
    expect(toPixels(remembered, 1200)).toEqual({ x: -300, y: 120 }); // 두 배 확대
    expect(toPixels(undefined, 1200)).toEqual({ x: 0, y: 0 });
  });

  it("연결선은 고른 곳의 오른쪽 끝 가운데에서 칩의 가장 가까운 가장자리 가운데로 간다", () => {
    const anchor = { left: 100, top: 200, right: 300, bottom: 220 };
    // 칩이 오른쪽에 있으면 칩의 왼쪽 가장자리로
    expect(leaderLine(anchor, { left: 500, top: 190, width: 120, height: 30 })).toEqual({ x1: 300, y1: 210, x2: 500, y2: 205 });
    // 칩을 고른 곳 왼쪽으로 옮기면 고른 곳의 왼쪽 끝에서 칩의 오른쪽 가장자리로
    expect(leaderLine(anchor, { left: 0, top: 300, width: 60, height: 30 })).toEqual({ x1: 100, y1: 210, x2: 60, y2: 315 });
  });

  it("칩이 고른 곳과 가로로 겹치면 위·아래로 잇고, 고른 곳 위에 겹쳐 있으면 긋지 않는다 (E2E에서 찾음: 선이 둘을 가로질렀다)", () => {
    const anchor = { left: 100, top: 200, right: 300, bottom: 220 };
    // 아래: 고른 곳 아래 끝(칩 가운데의 가로 위치, 고른 곳 안으로 맞춤)에서 칩 위 가장자리 가운데로
    expect(leaderLine(anchor, { left: 250, top: 280, width: 200, height: 30 })).toEqual({ x1: 300, y1: 220, x2: 350, y2: 280 });
    // 위
    expect(leaderLine(anchor, { left: 120, top: 100, width: 100, height: 30 })).toEqual({ x1: 170, y1: 200, x2: 170, y2: 130 });
    // 겹침
    expect(leaderLine(anchor, { left: 150, top: 195, width: 300, height: 30 })).toBeNull();
  });
});
