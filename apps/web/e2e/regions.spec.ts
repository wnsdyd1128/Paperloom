/**
 * W04a · 그림·표·수식 영역 선택 (G2 R13, IMPL §10.6).
 *
 * 1) 저장: 영역 모드에서 좌표 fixture의 두 색 사각형을 끌면 quad 하나가 그 사각형의 정규화 좌표와
 *    1 CSS px 안에서 같고, 고른 종류로 저장된다. 회전·확대된 보기에서 끌어도 같다.
 * 2) 재표시: 보기 회전 4 × 확대 4 (× DPR 3 project)에서 저장된 영역 표시가 사각형의 실제 위치와 2 CSS px 안이다.
 *    실제 위치는 PDF.js를 거치지 않고 fixture 좌표·쪽 요소 상자·회전으로 계산한다.
 * 3) 영역 이미지: 목록의 미리보기가 그 사각형이며, /Rotate 90 쪽에서는 왼쪽(빨강)이 위에 온다.
 *
 * 영역을 고르면 그 곁에 도구줄(종류 그림·표·수식, 설명, AI에게 질문, 주석, 그림 복사)이 뜬다 (docs/UI_PLAN.md U2).
 * 고른 영역의 quad는 쪽에 그린 선택 표시(data-quad)에서 읽는다.
 */
import { expect, type Page, test } from "@playwright/test";

import {
  clearAnnotations,
  EXPECTED,
  GEOMETRY_PDF,
  openFixture,
  openPanel,
  regionToolbar,
  saveNote,
  selectAndRead,
  selectionMarks,
  setView,
  showPage,
  TARGETS,
  uploadPdf,
} from "./fixture";

const ROTATIONS = [0, 90, 180, 270];
const ZOOMS = [0.5, 1, 1.5, 2];
const CSS_UNITS = 96 / 72;
const MAX_REGION_DRIFT_PX = 1; // 끈 사각형 → 저장 quad (선택한 보기의 CSS px)
const MAX_REPROJECTION_ERROR_PX = 2; // PLAN A03
// 도구줄은 그림·표·수식만 고른다. 일반 영역(generic)은 주석 목록의 종류 바꾸기로 확인한다.
const KINDS = ["figure", "table", "equation", "figure", "table"] as const;
const KIND_LABELS = { figure: "그림", table: "표", equation: "수식" } as const;
const NOTES = ".note-list .annotation";

type Box = [number, number, number, number];

test("R13 영역을 저장하고 회전·확대·DPR에서 다시 그린다", async ({ page }, testInfo) => {
  const fixture = await uploadPdf(page, GEOMETRY_PDF, "geometry-matrix.pdf");
  await clearAnnotations(page, fixture.versionId);
  await openFixture(page);
  const ids: string[] = [];
  let maxDrift = 0;

  // 1) 쪽마다 기준 보기(0°, 100%)에서 사각형을 끌어 저장한다.
  await setView(page, 0, 1);
  for (const fixturePage of EXPECTED.pages) {
    const index = fixturePage.page_index;
    const quad = await drawRegion(page, index, fixturePage.region.normalized as Box, 0);
    const drift = await quadDriftPx(page, index, quad, fixturePage.region.normalized as Box);
    maxDrift = Math.max(maxDrift, drift);
    expect(drift, `${fixturePage.name} 끈 영역`).toBeLessThanOrEqual(MAX_REGION_DRIFT_PX);
    await chooseRegionKind(page, KIND_LABELS[KINDS[index]]);
    await regionToolbar(page).getByRole("button", { name: "주석" }).click();
    await saveNote(page, `영역 p${index + 1}`);
    await expect(regionModeButton(page)).toHaveAttribute("aria-pressed", "false");
    const item = page.locator(NOTES, { hasText: `영역 p${index + 1}` });
    ids.push((await item.getAttribute("data-annotation-id"))!);
    const anchor = await (await page.request.get(`/api/v1/anchors/${await item.getAttribute("data-anchor-id")}`)).json();
    expect([anchor.kind, anchor.quote, anchor.quads.length]).toEqual([KINDS[index], "", 1]);
  }

  // 회전·확대된 보기에서 끌어도 같은 영역이다 (저장하지 않고 패널의 quad만 본다).
  for (const [rotation, zoom] of [[90, 1.5], [270, 0.5]] as const) {
    await setView(page, rotation, zoom);
    const region = EXPECTED.pages[0].region.normalized as Box;
    const quad = await drawRegion(page, 0, region, rotation);
    const drift = await quadDriftPx(page, 0, quad, region);
    maxDrift = Math.max(maxDrift, drift);
    expect(drift, `plain 영역 @ ${rotation}° ${zoom * 100}%`).toBeLessThanOrEqual(MAX_REGION_DRIFT_PX);
    await page.keyboard.press("Escape");
    await expect(regionModeButton(page)).toHaveAttribute("aria-pressed", "false");
  }

  // 2) 재표시 행렬
  let maxError = 0;
  for (const rotation of ROTATIONS) {
    for (const zoom of ZOOMS) {
      await setView(page, rotation, zoom);
      for (const fixturePage of EXPECTED.pages) {
        const error = await regionError(page, fixturePage.page_index, ids[fixturePage.page_index], {
          region: fixturePage.region.normalized as Box,
          rotation: (fixturePage.rotation + rotation) % 360,
          zoom,
        });
        maxError = Math.max(maxError, error);
        expect(error, `${fixturePage.name} @ ${rotation}° ${zoom * 100}%`).toBeLessThanOrEqual(MAX_REPROJECTION_ERROR_PX);
      }
    }
  }

  // 3) 영역 이미지: 회전 없는 쪽은 왼쪽 빨강·오른쪽 파랑, /Rotate 90 쪽은 위 빨강·아래 파랑.
  await setView(page, 0, 1);
  await openPanel(page, "주석");
  for (const index of [0, 1]) {
    const colors = await previewColors(page, ids[index]);
    const { left, right } = EXPECTED.pages[index].region.colors;
    // 마우스로 끈 영역은 fixture 사각형과 1 CSS px 안이고 잘라 낼 때 바깥쪽 픽셀로 맞추므로 ±2 px (정확한 크기는 pytest)
    const expectedSize = index === 1 ? [60, 120] : [120, 60];
    colors.size.forEach((value, axis) =>
      expect(Math.abs(value - expectedSize[axis]), `${EXPECTED.pages[index].name} 미리보기 크기 ${colors.size}`).toBeLessThanOrEqual(2),
    );
    expectColor(colors.first, left);
    expectColor(colors.second, right);
  }

  // 종류는 목록에서 바꿀 수 있고(일반 영역 포함), 위치는 그대로다.
  const first = page.locator(`.annotation[data-annotation-id="${ids[0]}"]`);
  const anchorId = (await first.getAttribute("data-anchor-id"))!;
  for (const [kind, label] of [["table", "표"], ["generic", "영역"]] as const) {
    await first.getByLabel("영역 종류").selectOption(kind);
    await expect.poll(async () => (await (await page.request.get(`/api/v1/anchors/${anchorId}`)).json()).kind).toBe(kind);
    await expect(first.locator("img")).toHaveAttribute("alt", `${label} 영역, 1쪽`);
  }

  const summary = { project: testInfo.project.name, regions: ids.length, maxDrift, maxError };
  console.log(`W04a ${JSON.stringify(summary)}`);
  await testInfo.attach("w04a-summary", { body: JSON.stringify(summary, null, 2), contentType: "application/json" });
});

test("영역 모드: Esc로 끝내고, 짧은 클릭은 무시하고, 쪽 밖은 잘라내고, 텍스트 선택을 시작하지 않는다", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "dpr-1", "입력 처리는 DPR과 무관하다");
  await openFixture(page);
  await setView(page, 0, 1);
  await showPage(page, 0);
  const toggle = regionModeButton(page);
  await toggle.click();
  await expect(toggle).toHaveAttribute("aria-pressed", "true");

  const frame = (await page.locator('.page[data-page-number="1"]').boundingBox())!;
  // 짧은 클릭(6 px 미만)은 영역이 아니다.
  await page.mouse.move(frame.x + 100, frame.y + 100);
  await page.mouse.down();
  await page.mouse.move(frame.x + 103, frame.y + 102);
  await page.mouse.up();
  await expect(page.locator(".quad-overlay")).toHaveCount(0);
  await expect(regionToolbar(page)).toHaveCount(0);

  // 쪽 안에서 시작해 쪽 왼쪽 위 밖까지 끌면 쪽 경계에서 잘린다. 텍스트(표식) 위를 지나도 텍스트 선택은 생기지 않는다.
  await page.mouse.move(frame.x + 300, frame.y + 200);
  await page.mouse.down();
  await page.mouse.move(frame.x - 30, frame.y - 30, { steps: 6 });
  await page.mouse.up();
  await expect(regionToolbar(page)).toBeVisible();
  const quad: number[] = JSON.parse((await selectionMarks(page, 0).getAttribute("data-quad"))!);
  expect(quad[0]).toBeCloseTo(0, 6); // 왼쪽 위가 쪽 모서리
  expect(quad[1]).toBeCloseTo(0, 6);
  expect(quad[4]).toBeCloseTo(300 / frame.width, 2);
  expect(await page.evaluate(() => document.getSelection()?.toString() ?? "")).toBe("");
  await expect(page.locator('.page[data-page-number="1"] > .quad-overlay > .quad-mark')).toHaveCount(1);

  await page.keyboard.press("Escape");
  await expect(toggle).toHaveAttribute("aria-pressed", "false");
  await expect(page.locator(".reader-scroll.region-mode")).toHaveCount(0);
});

test("그림을 누르면 일반 PDF 뷰어처럼 그 그림이 영역으로 골라진다", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "dpr-1", "좌표 변환은 R13 행렬이 DPR별로 확인한다");
  const fixture = await uploadPdf(page, GEOMETRY_PDF, "geometry-matrix.pdf");
  await clearAnnotations(page, fixture.versionId);
  await openFixture(page);
  await setView(page, 0, 1);
  const panelQuad = (index: number) => selectionMarks(page, index);

  // 그림 밖(빈 곳)을 누르면 아무것도 고르지 않는다.
  await showPage(page, 0);
  const frame = (await page.locator('.page[data-page-number="1"]').boundingBox())!;
  await page.mouse.click(frame.x + frame.width * 0.3, frame.y + frame.height * 0.7);
  await expect(page.locator(".quad-overlay")).toHaveCount(0);

  // 그림 위에 올리면 테두리가 보이고, 누르면 서버가 찾은 그림 상자(두 색 사각형)가 그대로 영역이 된다.
  for (const [index, rotation, zoom] of [[0, 0, 1], [1, 90, 1.5]] as const) {
    await setView(page, rotation, zoom);
    const region = EXPECTED.pages[index].region.normalized as Box;
    const center = await regionCenter(page, index, region, (EXPECTED.pages[index].rotation + rotation) % 360);
    await page.mouse.move(center.x, center.y);
    await expect(page.locator(`.page[data-page-number="${index + 1}"] > .figure-hover .quad-mark`)).toBeVisible();
    await expect(page.locator(".reader-scroll.over-figure")).toHaveCount(1);
    await page.mouse.click(center.x, center.y);
    await expect(panelQuad(index)).toHaveCount(1);
    const quad: number[] = JSON.parse((await panelQuad(index).getAttribute("data-quad"))!);
    const [u0, v0, u1, v1] = region;
    expect(quad).toEqual([u0, v0, u1, v0, u1, v1, u0, v1].map((value) => expect.closeTo(value, 9)));
  }

  // 영역 모드에서도 누르면 그 그림을 고른다(끌기 없이).
  await setView(page, 0, 1);
  await regionModeButton(page).click();
  const cropped = EXPECTED.pages[2].region.normalized as Box;
  const center = await regionCenter(page, 2, cropped, 0);
  await page.mouse.click(center.x, center.y);
  await expect(panelQuad(2)).toHaveCount(1);

  // 그림 종류로 저장된다.
  await expect(regionToolbar(page).getByRole("radio", { name: "그림" })).toBeChecked();
  await regionToolbar(page).getByRole("button", { name: "주석" }).click();
  await saveNote(page);
  const anchorId = await page.locator(NOTES).first().getAttribute("data-anchor-id");
  const anchor = await (await page.request.get(`/api/v1/anchors/${anchorId}`)).json();
  expect([anchor.kind, anchor.page_index]).toEqual(["figure", 2]);
});

test("선택한 그림은 Ctrl+C로 이미지가 복사되고, 텍스트 선택·메모 칸의 Ctrl+C는 그대로 텍스트를 복사한다", async ({
  page,
}, testInfo) => {
  test.skip(testInfo.project.name !== "dpr-1", "클립보드 처리는 DPR과 무관하다");
  await page.context().grantPermissions(["clipboard-read", "clipboard-write"]);
  await openFixture(page);
  await setView(page, 0, 1);

  // 그림을 누르고 Ctrl+C → 클립보드에 그림 이미지(PNG, PDF 1 pt당 2 px, 왼쪽 빨강·오른쪽 파랑)
  const region = EXPECTED.pages[0].region;
  const center = await regionCenter(page, 0, region.normalized as Box, 0);
  await page.mouse.click(center.x, center.y);
  await expect(selectionMarks(page, 0)).toHaveCount(1);
  await page.keyboard.press("Control+c");
  await expect(page.getByText("그림을 클립보드에 복사했습니다.")).toBeVisible();
  const image = (await clipboardImage(page))!;
  expect(image.type).toBe("image/png");
  expect(image.size).toEqual([region.pdf_rect[2] * 2, region.pdf_rect[3] * 2]);
  expectColor(image.left, region.colors.left);
  expectColor(image.right, region.colors.right);

  // 도구줄의 "그림 복사" 단추도 같다.
  await page.evaluate(() => navigator.clipboard.writeText("비움"));
  await regionToolbar(page).getByRole("button", { name: /그림 복사/ }).click();
  // 앞 복사의 안내가 남아 있으므로 안내가 아니라 클립보드 내용이 바뀔 때까지 기다린다.
  await expect
    .poll(async () => (await clipboardImage(page))?.size)
    .toEqual([region.pdf_rect[2] * 2, region.pdf_rect[3] * 2]);

  // 그림이 선택된 채 메모 창에서 Ctrl+C → 메모 글을 복사한다.
  await page.mouse.click(center.x, center.y);
  await regionToolbar(page).getByRole("button", { name: "주석" }).click();
  const memo = page.getByRole("form", { name: "주석 쓰기" }).getByLabel("메모");
  await memo.fill("메모 글");
  await memo.selectText();
  await page.keyboard.press("Control+c");
  expect(await page.evaluate(() => navigator.clipboard.readText())).toBe("메모 글");

  // 텍스트를 선택하면 Ctrl+C는 텍스트 복사다.
  await selectAndRead(page, TARGETS[0]);
  await page.keyboard.press("Control+c");
  expect(await page.evaluate(() => navigator.clipboard.readText())).toBe(TARGETS[0].texts[0]);
});

/** 클립보드의 PNG를 읽어 크기와 왼쪽·오른쪽 4분의 1 지점의 색을 잰다. */
async function clipboardImage(page: Page) {
  return page.evaluate(async () => {
    const [item] = await navigator.clipboard.read();
    const type = item.types.find((name) => name.startsWith("image/"));
    if (!type) return null; // 아직 이미지가 아니다
    const bitmap = await createImageBitmap(await item.getType(type));
    const canvas = document.createElement("canvas");
    canvas.width = bitmap.width;
    canvas.height = bitmap.height;
    const context = canvas.getContext("2d")!;
    context.drawImage(bitmap, 0, 0);
    const sample = (x: number, y: number) => [...context.getImageData(Math.floor(x), Math.floor(y), 1, 1).data.slice(0, 3)];
    return {
      type,
      size: [bitmap.width, bitmap.height],
      left: sample(bitmap.width / 4, bitmap.height / 2),
      right: sample((3 * bitmap.width) / 4, bitmap.height / 2),
    };
  });
}

/** 그림 영역의 화면 가운데 좌표. 쪽을 보이게 하고 그 영역이 본문 영역 가운데 오도록 스크롤한다. */
async function regionCenter(page: Page, pageIndex: number, region: Box, totalRotation: number) {
  await showPage(page, pageIndex);
  const box = displayedBox(region, totalRotation);
  await page.evaluate(
    ({ pageIndex, box }) => {
      const pageDiv = document.querySelector(`.page[data-page-number="${pageIndex + 1}"]`)!.getBoundingClientRect();
      const container = document.querySelector(".reader-scroll")!;
      const view = container.getBoundingClientRect();
      container.scrollLeft += pageDiv.left + ((box[0] + box[2]) / 2) * pageDiv.width - (view.left + view.width / 2);
      container.scrollTop += pageDiv.top + ((box[1] + box[3]) / 2) * pageDiv.height - (view.top + view.height / 2);
    },
    { pageIndex, box },
  );
  const frame = (await page.locator(`.page[data-page-number="${pageIndex + 1}"]`).boundingBox())!;
  return { x: frame.x + ((box[0] + box[2]) / 2) * frame.width, y: frame.y + ((box[1] + box[3]) / 2) * frame.height };
}

/** 회전 전 정규화 상자를 보기 회전(시계 방향)을 적용한 쪽 화면의 비율 상자로 바꾼다. */
function displayedBox([u0, v0, u1, v1]: Box, rotation: number): Box {
  switch (rotation) {
    case 90:
      return [1 - v1, u0, 1 - v0, u1];
    case 180:
      return [1 - u1, 1 - v1, 1 - u0, 1 - v0];
    case 270:
      return [v0, 1 - u1, v1, 1 - u0];
    default:
      return [u0, v0, u1, v1];
  }
}

/** 영역이 본문 영역 가운데 오도록 스크롤한 뒤 영역 모드에서 그 사각형을 끈다. 선택 표시의 quad를 돌려준다. */
async function drawRegion(page: Page, pageIndex: number, region: Box, viewRotation: number): Promise<number[]> {
  await showPage(page, pageIndex);
  const totalRotation = (EXPECTED.pages[pageIndex].rotation + viewRotation) % 360;
  const pageDiv = page.locator(`.page[data-page-number="${pageIndex + 1}"]`);
  await page.evaluate(
    ({ pageIndex, box }) => {
      const pageDiv = document.querySelector(`.page[data-page-number="${pageIndex + 1}"]`)!.getBoundingClientRect();
      const container = document.querySelector(".reader-scroll")!;
      const view = container.getBoundingClientRect();
      const centerX = pageDiv.left + ((box[0] + box[2]) / 2) * pageDiv.width;
      const centerY = pageDiv.top + ((box[1] + box[3]) / 2) * pageDiv.height;
      container.scrollLeft += centerX - (view.left + view.width / 2);
      container.scrollTop += centerY - (view.top + view.height / 2);
    },
    { pageIndex, box: displayedBox(region, totalRotation) },
  );
  const toggle = regionModeButton(page);
  if ((await toggle.getAttribute("aria-pressed")) !== "true") await toggle.click();
  const frame = (await pageDiv.boundingBox())!;
  const [du0, dv0, du1, dv1] = displayedBox(region, totalRotation);
  await page.mouse.move(frame.x + du0 * frame.width, frame.y + dv0 * frame.height);
  await page.mouse.down();
  await page.mouse.move(frame.x + du1 * frame.width, frame.y + dv1 * frame.height, { steps: 8 });
  await page.mouse.up();
  const item = selectionMarks(page, pageIndex);
  await expect(item).toHaveCount(1);
  await expect(regionToolbar(page)).toBeVisible();
  return JSON.parse((await item.getAttribute("data-quad"))!);
}

/** 머리의 "영역 설명" (영역 선택 모드) */
function regionModeButton(page: Page) {
  return page.getByRole("button", { name: "영역 설명" });
}

/** 도구줄에서 영역 종류를 고른다 (단추 모양의 라디오) */
async function chooseRegionKind(page: Page, label: string) {
  await regionToolbar(page).locator("label.seg-opt", { hasText: new RegExp(`^${label}$`) }).click();
  await expect(regionToolbar(page).getByRole("radio", { name: label })).toBeChecked();
}

/** 선택 표시 quad와 기대 영역의 차이 (선택한 보기의 CSS px, 네 변 중 최대). */
async function quadDriftPx(page: Page, pageIndex: number, quad: number[], [u0, v0, u1, v1]: Box): Promise<number> {
  const frame = (await page.locator(`.page[data-page-number="${pageIndex + 1}"]`).boundingBox())!;
  // 회전 전 u는 쪽 폭과 높이 중 어느 쪽에 놓이든 같은 길이다: 쪽의 pt 크기 × 확대 비율로 잰다.
  const [x0, y0, x1, y1] = EXPECTED.pages[pageIndex].view_box;
  const pxPerPoint = Math.max(frame.width, frame.height) / Math.max(x1 - x0, y1 - y0);
  const size = [(x1 - x0) * pxPerPoint, (y1 - y0) * pxPerPoint];
  const expected = [u0, v0, u1, v0, u1, v1, u0, v1];
  return Math.max(...quad.map((value, index) => Math.abs(value - expected[index]) * size[index % 2]));
}

/**
 * 저장된 영역 표시와 사각형의 실제 위치 차이 (CSS px, 네 변 중 최대).
 * PDF.js가 쪽을 다시 그리며 표시 층을 잠깐 지울 수 있으므로, 층의 viewport 표시와 위치를 한 번에 읽고
 * 이번 보기로 그려진 표시가 잡힐 때까지 다시 잰다.
 */
async function regionError(
  page: Page,
  pageIndex: number,
  annotationId: string,
  { region, rotation, zoom }: { region: Box; rotation: number; zoom: number },
): Promise<number> {
  await showPage(page, pageIndex);
  const [du0, dv0, du1, dv1] = displayedBox(region, rotation);
  let error = Infinity;
  await expect
    .poll(
      async () => {
        const measured = await page.evaluate(
          ({ pageIndex, annotationId }) => {
            const pageDiv = document.querySelector(`.page[data-page-number="${pageIndex + 1}"]`)!;
            const layer = pageDiv.querySelector<HTMLElement>(":scope > .annotation-overlay");
            const mark = layer?.querySelector(`.quad-mark[data-annotation-id="${annotationId}"]`);
            if (!layer || !mark) return null;
            const frame = pageDiv.getBoundingClientRect();
            const box = mark.getBoundingClientRect();
            return {
              scale: Number(layer.dataset.scale),
              rotation: Number(layer.dataset.rotation),
              frame: { x: frame.x, y: frame.y, width: frame.width, height: frame.height },
              mark: { left: box.left, top: box.top, right: box.right, bottom: box.bottom },
            };
          },
          { pageIndex, annotationId },
        );
        // 이번 보기로 다시 그린 표시만 잰다 (이전 보기끼리 비교하는 거짓 통과 방지).
        if (!measured || measured.rotation !== rotation || Math.abs(measured.scale - zoom * CSS_UNITS) > 1e-9) {
          return Infinity;
        }
        const { frame, mark } = measured;
        error = Math.max(
          Math.abs(mark.left - (frame.x + du0 * frame.width)),
          Math.abs(mark.top - (frame.y + dv0 * frame.height)),
          Math.abs(mark.right - (frame.x + du1 * frame.width)),
          Math.abs(mark.bottom - (frame.y + dv1 * frame.height)),
        );
        return error;
      },
      { message: `p${pageIndex + 1} ${rotation}° ${zoom * 100}% 영역 표시` },
    )
    .toBeLessThanOrEqual(MAX_REPROJECTION_ERROR_PX);
  return error;
}

/** 목록 미리보기 이미지의 크기와, 처음·나중 절반 가운데 색 (가로가 길면 왼쪽·오른쪽, 세로가 길면 위·아래). */
async function previewColors(page: Page, annotationId: string) {
  const image = page.locator(`.annotation[data-annotation-id="${annotationId}"] img`);
  await image.scrollIntoViewIfNeeded();
  await expect.poll(() => image.evaluate((element: HTMLImageElement) => element.complete && element.naturalWidth > 0)).toBe(true);
  return image.evaluate((element: HTMLImageElement) => {
    const canvas = document.createElement("canvas");
    canvas.width = element.naturalWidth;
    canvas.height = element.naturalHeight;
    const context = canvas.getContext("2d")!;
    context.drawImage(element, 0, 0);
    const sample = (x: number, y: number) => [...context.getImageData(Math.floor(x), Math.floor(y), 1, 1).data.slice(0, 3)];
    const { width, height } = canvas;
    const wide = width >= height;
    return {
      size: [width, height],
      first: wide ? sample(width / 4, height / 2) : sample(width / 2, height / 4),
      second: wide ? sample((3 * width) / 4, height / 2) : sample(width / 2, (3 * height) / 4),
    };
  });
}

function expectColor(actual: number[], expected: number[]) {
  actual.forEach((value, index) => expect(Math.abs(value - expected[index]), `색 ${actual} ≈ ${expected}`).toBeLessThanOrEqual(20));
}
