/** 좌표 계약 fixture의 PDF.js 쪽 검증 (IMPL §6.2). 서버 쪽은 tests/contract/test_geometry_fixture.py. */
import { readFileSync } from "node:fs";

import { getDocument, GlobalWorkerOptions, type PDFPageProxy } from "pdfjs-dist/legacy/build/pdf.mjs";
import { beforeAll, describe, expect, it } from "vitest";

import { boxToQuad, cssRectToBox, cssToNormalized, mergeLines, normalizedToCss, quadToCssRect } from "./geometry";

type FixturePage = {
  page_index: number;
  name: string;
  view_box: number[];
  rotation: number;
  user_unit: number;
  markers: { text: string; pdf_point: [number, number]; normalized: [number, number]; advance_width: number }[];
};

const FIXTURE_DIR = new URL("../../../../../tests/fixtures/pdf-layout/", import.meta.url);
const EXPECTED: { pages: FixturePage[] } = JSON.parse(readFileSync(new URL("geometry-matrix.json", FIXTURE_DIR), "utf8"));
const CSS_UNITS = 96 / 72; // PDF.js PixelsPerInch.PDF_TO_CSS_UNITS
const ROTATIONS = [0, 90, 180, 270];
const ZOOMS = [0.5, 1, 1.5, 2];
const MATRIX = ROTATIONS.flatMap((rotation) => ZOOMS.map((zoom) => [rotation, zoom] as const));

GlobalWorkerOptions.workerSrc = import.meta.resolve("pdfjs-dist/legacy/build/pdf.worker.mjs");

let pdfPages: PDFPageProxy[] = [];

beforeAll(async () => {
  const data = new Uint8Array(readFileSync(new URL("geometry-matrix.pdf", FIXTURE_DIR)));
  const document = await getDocument({ data }).promise;
  pdfPages = await Promise.all(EXPECTED.pages.map((page) => document.getPage(page.page_index + 1)));
});

function viewportFor(page: FixturePage, extraRotation: number, zoom: number) {
  const pdfPage = pdfPages[page.page_index];
  // PDFViewer와 같은 방식: 전체 회전 = 페이지 /Rotate + 보기 회전
  return pdfPage.getViewport({ scale: zoom * CSS_UNITS, rotation: (pdfPage.rotate + extraRotation) % 360 });
}

describe.each(EXPECTED.pages)("$name", (page) => {
  it("PDF.js의 view box·회전·UserUnit이 contract와 같다", () => {
    const pdfPage = pdfPages[page.page_index];
    expect(pdfPage.view).toEqual(page.view_box);
    expect(pdfPage.rotate).toBe(page.rotation);
    expect(pdfPage.userUnit).toBe(page.user_unit);
  });

  it("PDF.js 텍스트 항목의 폭이 fixture의 글자 폭과 같다", async () => {
    const { items } = await pdfPages[page.page_index].getTextContent();
    for (const marker of page.markers) {
      const item = items.find((candidate) => "str" in candidate && candidate.str === marker.text);
      expect(item && "width" in item ? item.width : NaN).toBeCloseTo(marker.advance_width, 2);
    }
  });

  it.each(MATRIX)("보기 회전 %i° · 확대 %f: 표식의 CSS 위치가 contract 정규화 좌표로 돌아온다", (rotation, zoom) => {
    const viewport = viewportFor(page, rotation, zoom);
    for (const marker of page.markers) {
      const [x, y] = viewport.convertToViewportPoint(...marker.pdf_point);
      expect(x).toBeGreaterThanOrEqual(0);
      expect(y).toBeGreaterThanOrEqual(0);
      expect(x).toBeLessThanOrEqual(viewport.width);
      expect(y).toBeLessThanOrEqual(viewport.height);

      const [u, v] = cssToNormalized(viewport, x, y);
      expect(u).toBeCloseTo(marker.normalized[0], 9);
      expect(v).toBeCloseTo(marker.normalized[1], 9);

      const [backX, backY] = normalizedToCss(viewport, ...marker.normalized);
      expect(backX).toBeCloseTo(x, 6);
      expect(backY).toBeCloseTo(y, 6);
    }
  });
});

describe("선택 사각형 → 줄 quad", () => {
  const plain = () => EXPECTED.pages[0];

  it.each(MATRIX)("보기 회전 %i° · 확대 %f에서 같은 CSS 영역은 같은 정규화 상자가 된다", (rotation, zoom) => {
    const base = viewportFor(plain(), 0, 1);
    const target = { u0: 0.1, v0: 0.2, u1: 0.4, v1: 0.25 };
    const viewport = viewportFor(plain(), rotation, zoom);

    const rect = quadToCssRect(viewport, boxToQuad(target));
    const box = cssRectToBox(viewport, rect);

    for (const key of ["u0", "v0", "u1", "v1"] as const) expect(box[key]).toBeCloseTo(target[key], 9);
    expect(quadToCssRect(base, boxToQuad(box)).left).toBeCloseTo(quadToCssRect(base, boxToQuad(target)).left, 6);
  });

  it("같은 줄 조각은 합치고 다른 줄은 나눈다", () => {
    const lines = mergeLines([
      { u0: 0.3, v0: 0.1, u1: 0.5, v1: 0.12 },
      { u0: 0.1, v0: 0.101, u1: 0.29, v1: 0.121 },
      { u0: 0.1, v0: 0.13, u1: 0.4, v1: 0.15 },
    ]);

    expect(lines).toEqual([
      { u0: 0.1, v0: 0.1, u1: 0.5, v1: 0.121 },
      { u0: 0.1, v0: 0.13, u1: 0.4, v1: 0.15 },
    ]);
  });

  it("페이지 밖으로 나간 선택은 0~1로 자른다", () => {
    const viewport = viewportFor(plain(), 0, 1);
    const box = cssRectToBox(viewport, { left: -50, top: -10, right: 30, bottom: 20 });

    expect(box.u0).toBe(0);
    expect(box.v0).toBe(0);
    expect(box.u1).toBeGreaterThan(0);
  });
});
