/**
 * PLAN A03 · 좌표 재표시 행렬: 보기 회전 4 × 확대 4 × devicePixelRatio 3 (project).
 *
 * 1) 재표시: 기준 보기(0°, 100%)에서 선택한 quad를 다른 보기로 다시 그렸을 때,
 *    같은 텍스트의 실제 위치와의 차이가 2 CSS px 이내여야 한다.
 * 2) 안정성: 어느 보기에서 선택해도 quad가 기준과 같아야 한다. 허용 차이는 선택한 보기에서 1 CSS px다.
 *    선택의 정밀도는 선택할 때의 화면 픽셀보다 좋아질 수 없다 (작은 확대에서 텍스트 위치가 픽셀에 맞춰진다).
 * 3) 절대 위치: 기준 quad가 fixture의 PDF 좌표(기준선 시작점)를 포함해야 한다.
 */
import { expect, test } from "@playwright/test";

import {
  CSS_UNITS,
  EXPECTED,
  type FixturePage,
  type Marker,
  MAX_REPROJECTION_ERROR_PX,
  openFixture,
  type Quad,
  reprojectionError,
  selectAndRead,
  SELECTION_STATUS,
  selectionMarks,
  selectionStats,
  setView,
  showPage,
  TARGETS,
  zoomButton,
} from "./fixture";

const ROTATIONS = [0, 90, 180, 270];
const ZOOMS = [0.5, 1, 1.5, 2];
const MAX_SELECTION_DRIFT_PX = 1;

test("A03 좌표 재표시 행렬", async ({ page }, testInfo) => {
  selectionStats.retries = 0;
  await openFixture(page);
  const baseQuads = new Map<string, Quad[]>();
  let maxError = 0;
  let maxDriftPx = 0;
  let maxDriftNormalized = 0;

  // 1) 기준 보기에서 선택한 quad를 16개 보기로 다시 그린다.
  for (const target of TARGETS) {
    await setView(page, 0, 1);
    const quads = await selectAndRead(page, target);
    expect(quads).toHaveLength(target.texts.length);
    const viewBox = EXPECTED.pages[target.pageIndex].view_box;
    target.markers.forEach((marker, line) => {
      expectContainsBaseline(quads[line], marker);
      expectMatchesTextSize(quads[line], marker, viewBox);
    });
    baseQuads.set(target.label, quads);
    await page.evaluate(() => document.getSelection()?.removeAllRanges()); // 저장된 quad만 남긴다

    for (const rotation of ROTATIONS) {
      for (const zoom of ZOOMS) {
        await setView(page, rotation, zoom);
        const error = await reprojectionError(page, target, rotation, zoom);
        maxError = Math.max(maxError, error);
        expect(error, `${target.label} @ ${rotation}° ${zoom * 100}%`).toBeLessThanOrEqual(MAX_REPROJECTION_ERROR_PX);
      }
    }
  }

  // 2) 모든 보기에서 다시 선택해도 quad가 기준과 같다 (선택한 보기에서 1 CSS px 이내).
  for (const rotation of ROTATIONS) {
    for (const zoom of ZOOMS) {
      await setView(page, rotation, zoom);
      for (const target of TARGETS) {
        const quads = await selectAndRead(page, target);
        const drift = quadDrift(quads, baseQuads.get(target.label)!, EXPECTED.pages[target.pageIndex], zoom);
        maxDriftPx = Math.max(maxDriftPx, drift.px);
        maxDriftNormalized = Math.max(maxDriftNormalized, drift.normalized);
        expect(drift.px, `${target.label} @ ${rotation}° ${zoom * 100}%`).toBeLessThanOrEqual(MAX_SELECTION_DRIFT_PX);
      }
    }
  }

  const summary = {
    project: testInfo.project.name,
    targets: TARGETS.length,
    maxError,
    maxDriftPx,
    maxDriftNormalized,
    selectionRetries: selectionStats.retries,
  };
  console.log(`A03 ${JSON.stringify(summary)}`);
  await testInfo.attach("a03-summary", { body: JSON.stringify(summary, null, 2), contentType: "application/json" });
});

test("마우스 드래그로 두 줄을 선택하고 회전해도 표시가 따라온다", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "dpr-1", "입력 경로 확인은 한 번이면 충분하다");
  await openFixture(page);
  await setView(page, 0, 1);
  await showPage(page, 0);
  const [first, second] = EXPECTED.pages[0].markers.map((marker) =>
    page.locator('.page[data-page-number="1"] .textLayer span', { hasText: marker.text }),
  );
  // 쪽을 가운데 맞추면 1쪽 첫 줄이 스크롤 영역 위 가장자리 가까이 온다. 거기서 드래그하면 브라우저가 선택 중
  // 자동 스크롤을 해 놓는 지점이 다른 줄이 된다(간헐 실패, W05 기록 §9). 줄을 가운데로 옮긴 뒤 잰다.
  await first.evaluate((element) => element.scrollIntoView({ block: "center" }));
  const start = (await first.boundingBox())!;
  const end = (await second.boundingBox())!;

  await page.mouse.move(start.x + 1, start.y + start.height / 2);
  await page.mouse.down();
  await page.mouse.move(end.x + end.width - 1, end.y + end.height / 2, { steps: 12 });
  await page.mouse.up();

  await expect(page.locator(SELECTION_STATUS)).toContainText("1쪽에서 2줄을 골랐습니다");
  await expect(selectionMarks(page, 0)).toHaveCount(2);
  await zoomButton(page).click();
  await page.getByRole("menuitem", { name: /시계 방향으로 회전/ }).click();
  await expect(page.locator('.page[data-page-number="1"] > .quad-overlay')).toHaveAttribute("data-rotation", "90");
  await showPage(page, 0);
  await page.screenshot({ path: testInfo.outputPath("drag-select-rotate-90.png") });
});

test("두 쪽에 걸친 선택은 쪽별 quad로 나뉜다", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "dpr-1", "DOM 분할 로직은 DPR과 무관하다");
  await openFixture(page);
  await setView(page, 0, 0.5); // 1쪽과 2쪽이 함께 그려지는 확대
  const spanOn = (pageNumber: number, text: string) =>
    page.locator(`.page[data-page-number="${pageNumber}"] .textLayer:not([hidden]) span`, { hasText: text });
  const from = spanOn(1, EXPECTED.pages[0].markers[1].text);
  const to = spanOn(2, EXPECTED.pages[1].markers[0].text);
  await expect(from).toBeVisible();
  await expect(to).toBeVisible();

  const start = await from.elementHandle();
  await to.evaluate((end, start) => {
    const range = document.createRange();
    range.setStart(start!.firstChild!, 0);
    range.setEnd(end.firstChild!, end.firstChild!.textContent!.length);
    const selection = document.getSelection()!;
    selection.removeAllRanges();
    selection.addRange(range);
  }, start);

  await expect(page.locator(".quad-overlay")).toHaveCount(2);
  await expect(selectionMarks(page, 0)).toHaveCount(1);
  await expect(selectionMarks(page, 1)).toHaveCount(1);
  await expect(page.locator(SELECTION_STATUS)).toHaveText("여러 쪽에 걸친 선택은 주석으로 저장할 수 없습니다. 쪽마다 따로 선택하세요.");
});

/** 기준 quad와의 최대 차이. px는 선택한 보기(zoom)에서 그 차이가 차지하는 CSS px다. */
function quadDrift(quads: Quad[], base: Quad[], fixturePage: FixturePage, zoom: number) {
  if (quads.length !== base.length) return { normalized: Infinity, px: Infinity };
  const [x0, y0, x1, y1] = fixturePage.view_box;
  const pxPerPoint = fixturePage.user_unit * zoom * CSS_UNITS;
  const pageSize = [(x1 - x0) * pxPerPoint, (y1 - y0) * pxPerPoint]; // 짝수 인덱스는 u, 홀수는 v
  const differences = quads.flatMap((quad, line) => quad.map((value, index) => [Math.abs(value - base[line][index]), index]));
  return {
    normalized: Math.max(...differences.map(([difference]) => difference)),
    px: Math.max(...differences.map(([difference, index]) => difference * pageSize[index % 2])),
  };
}

/**
 * 선택 영역의 절대 크기가 PDF의 글자와 같은지: 폭은 글자 폭 합, 높이는 글꼴 크기.
 * text layer가 캔버스와 다른 글꼴로 폭을 재면 재표시는 text layer와 일치해도 실제 글자보다
 * 좁아지므로, text layer에 기대지 않는 fixture 값과 따로 비교한다.
 */
function expectMatchesTextSize(quad: Quad, marker: Marker, viewBox: number[]) {
  const widthPt = (quad[2] - quad[0]) * (viewBox[2] - viewBox[0]);
  const heightPt = (quad[5] - quad[1]) * (viewBox[3] - viewBox[1]);
  expect(Math.abs(widthPt - marker.advance_width) / marker.advance_width, `${marker.text} 폭`).toBeLessThan(0.015);
  expect(Math.abs(heightPt - EXPECTED.font_size) / EXPECTED.font_size, `${marker.text} 높이`).toBeLessThan(0.05);
}

/** 기준 quad가 표식의 기준선 시작점을 포함하는지 (회전·CropBox·UserUnit 정규화의 절대 검증). */
function expectContainsBaseline(quad: Quad, marker: Marker) {
  const [u, v] = marker.normalized;
  const [u0, v0, , , , v1] = quad;
  expect(Math.abs(u0 - u), `${marker.text} 시작 u`).toBeLessThan(0.01);
  expect(v, `${marker.text} 기준선 v`).toBeGreaterThan(v0);
  expect(v, `${marker.text} 기준선 v`).toBeLessThan(v1 + 0.005);
}
