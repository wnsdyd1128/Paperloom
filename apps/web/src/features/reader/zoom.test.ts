import { describe, expect, it } from "vitest";

import {
  DEFAULT_ZOOM,
  formatZoom,
  MAX_ZOOM,
  MIN_ZOOM,
  normalizeZoom,
  stepZoom,
  wheelZoomFactor,
  ZOOM_PRESETS,
  zoomKeyAction,
} from "./zoom";

const key = (key: string, modifiers: Partial<{ ctrlKey: boolean; metaKey: boolean; altKey: boolean }> = {}) => ({
  key,
  ctrlKey: false,
  metaKey: false,
  altKey: false,
  ...modifiers,
});

describe("stepZoom", () => {
  it("preset 사이를 한 단계씩 오가고 100%가 preset에 있다", () => {
    expect(ZOOM_PRESETS).toContain(DEFAULT_ZOOM);
    for (let index = 0; index < ZOOM_PRESETS.length - 1; index++) {
      expect(stepZoom(ZOOM_PRESETS[index], 1)).toBe(ZOOM_PRESETS[index + 1]);
      expect(stepZoom(ZOOM_PRESETS[index + 1], -1)).toBe(ZOOM_PRESETS[index]);
    }
  });

  it("범위 끝에서는 끝 값에 머문다", () => {
    expect(stepZoom(MAX_ZOOM, 1)).toBe(MAX_ZOOM);
    expect(stepZoom(MIN_ZOOM, -1)).toBe(MIN_ZOOM);
  });

  it("preset 밖의 값은 가까운 방향의 다음 preset으로 간다", () => {
    expect(stepZoom(1.728, 1)).toBe(1.75);
    expect(stepZoom(1.728, -1)).toBe(1.5);
    // preset과 0.1% 안이면 그 preset에 있는 것으로 본다
    expect(stepZoom(0.9999, 1)).toBe(1.1);
    expect(stepZoom(1.0001, -1)).toBe(0.9);
  });
});

describe("wheelZoomFactor", () => {
  it("휠 한 칸(100 px)마다 1.2배, 위로 굴리면 확대", () => {
    expect(wheelZoomFactor(-100, 0)).toBeCloseTo(1.2, 12);
    expect(wheelZoomFactor(100, 0)).toBeCloseTo(1 / 1.2, 12);
    expect(wheelZoomFactor(0, 0)).toBe(1);
  });

  it("줄 단위(한 칸 = 3줄)와 쪽 단위 휠도 한 칸이 같은 배율이다", () => {
    expect(wheelZoomFactor(-3, 1)).toBeCloseTo(1.2, 12);
    expect(wheelZoomFactor(-1, 2)).toBeCloseTo(1.2, 12);
  });

  it("이벤트가 합쳐져도(coalesce) 결과가 같다", () => {
    expect(wheelZoomFactor(-40, 0) * wheelZoomFactor(-60, 0)).toBeCloseTo(wheelZoomFactor(-100, 0), 12);
  });
});

describe("normalizeZoom", () => {
  it("범위를 자르고, 같은 칸만큼 확대·축소하면 원래 값으로 돌아온다", () => {
    expect(normalizeZoom(0.01)).toBe(MIN_ZOOM);
    expect(normalizeZoom(100)).toBe(MAX_ZOOM);
    let scale = DEFAULT_ZOOM;
    for (let notch = 0; notch < 3; notch++) scale = normalizeZoom(scale * wheelZoomFactor(-100, 0));
    expect(scale).toBe(1.728);
    for (let notch = 0; notch < 3; notch++) scale = normalizeZoom(scale * wheelZoomFactor(100, 0));
    expect(scale).toBe(1);
  });

  it("트랙패드 핀치의 작은 변화도 배율을 바꾼다", () => {
    for (const scale of [MIN_ZOOM, 1, MAX_ZOOM - 0.01]) {
      expect(normalizeZoom(scale * wheelZoomFactor(-1, 0))).toBeGreaterThan(scale);
    }
  });
});

describe("zoomKeyAction", () => {
  it("Ctrl 또는 Cmd와 +·=·-·0", () => {
    expect(zoomKeyAction(key("=", { ctrlKey: true }))).toBe("in");
    expect(zoomKeyAction(key("+", { ctrlKey: true }))).toBe("in");
    expect(zoomKeyAction(key("-", { ctrlKey: true }))).toBe("out");
    expect(zoomKeyAction(key("0", { ctrlKey: true }))).toBe("reset");
    expect(zoomKeyAction(key("0", { metaKey: true }))).toBe("reset");
  });

  it("수정 키가 없거나 Alt가 섞이거나 다른 키면 가로채지 않는다", () => {
    expect(zoomKeyAction(key("0"))).toBeNull();
    expect(zoomKeyAction(key("0", { ctrlKey: true, altKey: true }))).toBeNull();
    expect(zoomKeyAction(key("c", { ctrlKey: true }))).toBeNull();
    expect(zoomKeyAction(key("Control", { ctrlKey: true }))).toBeNull();
  });
});

it("formatZoom은 정수 퍼센트", () => {
  expect(formatZoom(1)).toBe("100%");
  expect(formatZoom(0.33)).toBe("33%");
  expect(formatZoom(1.728)).toBe("173%");
});
