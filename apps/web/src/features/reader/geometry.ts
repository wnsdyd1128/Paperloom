/**
 * 정본 좌표계의 웹 쪽 어댑터 (IMPL §6.1–6.2).
 *
 * 좌표는 회전 전 유효 view box 기준, 좌상단 원점, 0~1로 정규화한다. CSS 좌표는 반드시
 * PDF.js viewport 역변환으로 PDF 좌표로 바꾼 뒤 정규화한다. devicePixelRatio는 다루지 않는다
 * (렌더링 전용). 서버 쪽 같은 계약: backend/src/paperloom/reading/geometry.py
 */

/** 이 모듈이 쓰는 PDF.js PageViewport의 부분. */
export type ViewportLike = {
  readonly viewBox: readonly number[];
  convertToPdfPoint(x: number, y: number): number[];
  convertToViewportPoint(x: number, y: number): number[];
};

export type Point = readonly [number, number];

/** 정규화 공간의 축 정렬 상자. */
export type Box = Readonly<{ u0: number; v0: number; u1: number; v1: number }>;

/** 한 줄의 네 꼭짓점 (u, v): 좌상 → 우상 → 우하 → 좌하. anchor.v1의 `quads` 원소와 같다. */
export type Quad = readonly [number, number, number, number, number, number, number, number];

/** 페이지 요소 기준 CSS 사각형. */
export type CssRect = Readonly<{ left: number; top: number; right: number; bottom: number }>;

export function normalizePoint(viewBox: readonly number[], x: number, y: number): Point {
  const [x0, y0, x1, y1] = viewBox;
  return [(x - x0) / (x1 - x0), (y1 - y) / (y1 - y0)];
}

export function denormalizePoint(viewBox: readonly number[], u: number, v: number): Point {
  const [x0, y0, x1, y1] = viewBox;
  return [x0 + u * (x1 - x0), y1 - v * (y1 - y0)];
}

export function cssToNormalized(viewport: ViewportLike, x: number, y: number): Point {
  const [pdfX, pdfY] = viewport.convertToPdfPoint(x, y);
  return normalizePoint(viewport.viewBox, pdfX, pdfY);
}

export function normalizedToCss(viewport: ViewportLike, u: number, v: number): Point {
  const [pdfX, pdfY] = denormalizePoint(viewport.viewBox, u, v);
  const [x, y] = viewport.convertToViewportPoint(pdfX, pdfY);
  return [x, y];
}

/** CSS 사각형의 네 꼭짓점을 정규화한 뒤 감싸는 상자. 페이지 밖으로 나간 부분은 잘라낸다. */
export function cssRectToBox(viewport: ViewportLike, rect: CssRect): Box {
  const corners = [
    cssToNormalized(viewport, rect.left, rect.top),
    cssToNormalized(viewport, rect.right, rect.top),
    cssToNormalized(viewport, rect.right, rect.bottom),
    cssToNormalized(viewport, rect.left, rect.bottom),
  ];
  const us = corners.map(([u]) => clamp01(u));
  const vs = corners.map(([, v]) => clamp01(v));
  return { u0: Math.min(...us), v0: Math.min(...vs), u1: Math.max(...us), v1: Math.max(...vs) };
}

export function boxToQuad({ u0, v0, u1, v1 }: Box): Quad {
  return [u0, v0, u1, v0, u1, v1, u0, v1];
}

/** 현재 viewport에서 quad를 감싸는 CSS 사각형 (페이지 요소 기준). */
export function quadToCssRect(viewport: ViewportLike, quad: Quad): CssRect {
  const points = [0, 2, 4, 6].map((i) => normalizedToCss(viewport, quad[i], quad[i + 1]));
  const xs = points.map(([x]) => x);
  const ys = points.map(([, y]) => y);
  return { left: Math.min(...xs), top: Math.min(...ys), right: Math.max(...xs), bottom: Math.max(...ys) };
}

/**
 * 선택 조각을 줄 단위 상자로 합친다. 세로 범위가 짧은 쪽 높이의 절반 이상 겹치면 같은 줄로 본다.
 * 회전 전 좌표에서 비교하므로 화면 회전과 무관하다. 세로쓰기 텍스트는 v0.1 범위 밖이다.
 */
export function mergeLines(boxes: readonly Box[]): Box[] {
  const lines: Box[] = [];
  for (const box of [...boxes].sort((a, b) => a.v0 - b.v0 || a.u0 - b.u0)) {
    const last = lines.at(-1);
    const overlap = last ? Math.min(last.v1, box.v1) - Math.max(last.v0, box.v0) : 0;
    if (last && overlap >= 0.5 * Math.min(last.v1 - last.v0, box.v1 - box.v0)) {
      lines[lines.length - 1] = {
        u0: Math.min(last.u0, box.u0),
        v0: Math.min(last.v0, box.v0),
        u1: Math.max(last.u1, box.u1),
        v1: Math.max(last.v1, box.v1),
      };
    } else {
      lines.push(box);
    }
  }
  return lines;
}

function clamp01(value: number): number {
  return Math.min(1, Math.max(0, value));
}
