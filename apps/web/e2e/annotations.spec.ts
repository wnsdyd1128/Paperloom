/**
 * W04 · 원문 위치(Anchor)·주석·버전 고정 링크 (G2 R09–R11, R14). 서버 검증의 세부는 pytest가 맡는다.
 *
 * R09 저장·복귀: 선택을 메모와 함께 저장하고 새로고침하면 같은 버전·같은 위치로 돌아오고, 주석 표시가 글자와 맞는다.
 * R10 revision 충돌: 화면이 본 뒤 다른 곳에서 바뀐 주석을 고치면 거부되고 최신 내용을 다시 불러온다.
 * R11 버전 고정 링크: 링크의 버전을 그대로 열고 최신 버전으로 바꾸지 않는다. 맞지 않는 버전·위치는 알린다.
 * R14 첨자 추정: 첨자가 섞인 선택은 원문 인용과 추정 표기를 따로 보이고 따로 저장한다.
 *
 * 주석은 고른 글 곁의 메뉴에서 "주석"을 눌러 메모 창에서 저장하고, 사이드바 "주석" 패널에서 본다 (docs/UI_PLAN.md U2).
 */
import { readFileSync } from "node:fs";

import { expect, type Locator, type Page, test } from "@playwright/test";

import {
  chooseZoom,
  clearAnnotations,
  EXPECTED,
  FIXTURE_DIR,
  GEOMETRY_PDF,
  listAnnotations,
  MAX_REPROJECTION_ERROR_PX,
  menuItem,
  openFixture,
  openPanel,
  reprojectionError,
  saveNote,
  SELECTION_STATUS,
  selectAndRead,
  TARGETS,
  uploadPdf,
} from "./fixture";

type SubscriptLine = { name: string; v_range: [number, number]; text: string; display_quote: string | null };

const SUBSCRIPTS_PDF = readFileSync(new URL("subscripts.pdf", FIXTURE_DIR));
const SUBSCRIPTS: { lines: SubscriptLine[] } = JSON.parse(readFileSync(new URL("subscripts.json", FIXTURE_DIR), "utf8"));
const NOTES = ".note-list .annotation";

test("R09 저장한 주석은 새로고침 뒤 같은 버전·같은 위치로 돌아온다", async ({ page }, testInfo) => {
  const fixture = await uploadPdf(page, GEOMETRY_PDF, "geometry-matrix.pdf");
  await clearAnnotations(page, fixture.versionId);
  await openFixture(page);
  // UserUnit 2 쪽: 앞쪽들과 크기가 달라, 모든 쪽 크기를 안 뒤에 스크롤해야 제자리에 간다.
  const target = TARGETS.find((candidate) => candidate.pageIndex === 3)!;
  await selectAndRead(page, target);
  await saveSelection(page, "사용자 단위 표식 메모");

  await openPanel(page, "주석");
  const item = page.locator(NOTES);
  await expect(item).toHaveCount(1);
  await expect(item).toContainText("사용자 단위 표식 메모");
  const anchorId = (await item.getAttribute("data-anchor-id"))!;
  await expectPath(page, `/reader/${fixture.paperId}?version=${fixture.versionId}&anchor=${anchorId}`);
  // 저장한 선택은 주석 표시로 바뀐다.
  await expect(page.locator('.page[data-page-number="4"] > .annotation-overlay > .quad-mark')).toHaveCount(1);
  await expect(page.locator(".quad-overlay")).toHaveCount(0);

  await page.locator(".reader-scroll").evaluate((scroller) => scroller.scrollTo(0, 0));
  await page.reload();

  await expectPath(page, `/reader/${fixture.paperId}?version=${fixture.versionId}&anchor=${anchorId}`);
  const focused = page.locator('.page[data-page-number="4"] > .annotation-overlay > .quad-mark.is-focused');
  await expect(focused).toHaveCount(1);
  await expect(page.locator(`${NOTES}.is-focused`)).toContainText("사용자 단위 표식 메모");
  await expect.poll(() => isInsideScroller(page, focused), { message: "링크 위치로 스크롤" }).toBe(true);
  const error = await reprojectionError(page, target, 0, 1, "annotation-overlay");
  expect(error).toBeLessThanOrEqual(MAX_REPROJECTION_ERROR_PX);
  console.log(`W04 reload ${JSON.stringify({ project: testInfo.project.name, error })}`);

  // 목록의 원문 위치 링크를 누르면 다시 그 위치로 간다(패널은 새로고침 뒤에도 열려 있다).
  await page.locator(".reader-scroll").evaluate((scroller) => scroller.scrollTo(0, 0));
  await expect.poll(() => isInsideScroller(page, focused)).toBe(false);
  await item.getByRole("link").click();
  await expect.poll(() => isInsideScroller(page, focused)).toBe(true);
});

test("R10 그사이 바뀐 주석을 고치면 거부되고 최신 내용을 다시 불러온다", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "dpr-1", "revision 처리는 DPR과 무관하다");
  const fixture = await uploadPdf(page, GEOMETRY_PDF, "geometry-matrix.pdf");
  await clearAnnotations(page, fixture.versionId);
  await openFixture(page);
  await selectAndRead(page, TARGETS[0]);
  await saveSelection(page, "처음 메모");
  await openPanel(page, "주석");
  const item = page.locator(NOTES);
  await expect(item).toHaveAttribute("data-revision", "1");

  // 다른 창에서 먼저 고친다.
  const annotationId = (await item.getAttribute("data-annotation-id"))!;
  const other = await page.request.patch(`/api/v1/annotations/${annotationId}`, {
    data: { revision: 1, comment: "다른 창에서 고친 메모" },
  });
  expect(other.status()).toBe(200);

  await item.getByRole("button", { name: "메모 수정" }).click();
  await item.getByLabel("메모 수정").fill("화면에서 고친 메모");
  await item.getByRole("button", { name: "수정 저장" }).click();
  await expect(item.getByRole("alert")).toContainText("그사이 다른 곳에서");
  await expect(item).toHaveAttribute("data-revision", "2"); // 최신 목록을 다시 불러왔다
  await item.getByRole("button", { name: "취소" }).click();
  await expect(item.locator(".comment")).toHaveText("다른 창에서 고친 메모");

  // 최신 내용을 본 뒤에는 저장된다.
  await item.getByRole("button", { name: "메모 수정" }).click();
  await item.getByLabel("메모 수정").fill("다시 고친 메모");
  await item.getByRole("button", { name: "수정 저장" }).click();
  await expect(item.locator(".comment")).toHaveText("다시 고친 메모");
  await expect(item).toHaveAttribute("data-revision", "3");

  // 삭제는 확인을 받는다. 강조 표시도 사라지고(저장 직후라 주소에 있던 위치도 지운다), 서버의 원문 위치는 남는다.
  const anchorId = (await item.getAttribute("data-anchor-id"))!;
  await expectPath(page, `/reader/${fixture.paperId}?version=${fixture.versionId}&anchor=${anchorId}`);
  const highlights = page.locator(".annotation-overlay .quad-mark");
  await expect(highlights).toHaveCount(1);
  page.once("dialog", (dialog) => dialog.accept());
  await item.getByRole("button", { name: "삭제" }).click();
  await expect(page.getByText("저장한 주석이 없습니다.")).toBeVisible();
  await expect(highlights).toHaveCount(0);
  await expectPath(page, `/reader/${fixture.paperId}?version=${fixture.versionId}`);
  await page.reload();
  await expect(page.getByText("저장한 주석이 없습니다.")).toBeVisible();
  await expect(highlights).toHaveCount(0);
  expect((await listAnnotations(page, fixture.versionId)).length).toBe(0);
  expect((await page.request.get(`/api/v1/anchors/${anchorId}`)).status()).toBe(200);
});

test("R11 버전 고정 링크는 링크의 버전을 열고 최신 버전으로 바꾸지 않는다", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "dpr-1", "주소 처리는 DPR과 무관하다");
  const fixture = await uploadPdf(page, GEOMETRY_PDF, "geometry-matrix.pdf");
  await clearAnnotations(page, fixture.versionId);
  const anchorId = await createAnchorViaApi(page, fixture.versionId, "고정 링크 메모");

  // 이 논문에 더 새 버전이 있는 상황: 논문 조회가 다른 current_version을 돌려주게 한다.
  await page.route(`**/api/v1/papers/${fixture.paperId}`, async (route) => {
    const response = await route.fetch();
    const paper = await response.json();
    const newer = { ...paper.current_version, version_id: "newer-version", created_at: "2099-01-01T00:00:00Z" };
    await route.fulfill({ response, json: { ...paper, current_version: newer } });
  });
  const pdfPaths = new Set<string>();
  page.on("request", (request) => {
    const { pathname } = new URL(request.url());
    if (pathname.endsWith("/pdf")) pdfPaths.add(pathname);
  });

  await page.goto(`/reader/${fixture.paperId}?version=${fixture.versionId}&anchor=${anchorId}`);
  await expect(page.getByTestId("pinned-version-notice")).toBeVisible();
  await expect(page.locator('.page[data-page-number="1"] > .annotation-overlay > .quad-mark.is-focused')).toHaveCount(1);
  await expect(page.locator(`${NOTES}.is-focused`)).toContainText("고정 링크 메모");
  expect([...pdfPaths]).toEqual([`/api/v1/versions/${fixture.versionId}/pdf`]);
  await page.unrouteAll();

  // 버전이 없는 주소는 지금의 버전으로 고정해 둔다.
  await page.goto(`/reader/${fixture.paperId}`);
  await expectPath(page, `/reader/${fixture.paperId}?version=${fixture.versionId}`);
  await expect(page.getByTestId("pinned-version-notice")).toHaveCount(0);

  // 다른 논문의 버전, 다른 버전의 위치는 바꿔 열지 않고 알린다.
  const other = await uploadPdf(page, SUBSCRIPTS_PDF, "subscripts.pdf");
  await page.goto(`/reader/${fixture.paperId}?version=${other.versionId}`);
  await expect(page.getByText("링크의 버전이 이 논문에 속하지 않습니다.")).toBeVisible();
  await page.goto(`/reader/${other.paperId}?version=${other.versionId}&anchor=${anchorId}`);
  await expect(page.getByText("링크의 원문 위치를 이 버전에서 찾을 수 없습니다.")).toBeVisible();
  await page.goto(`/reader/no-such-paper?version=${fixture.versionId}`);
  await expect(page.getByText("링크의 논문이나 버전을 찾을 수 없습니다.")).toBeVisible();
});

test("여러 쪽에 걸친 선택은 주석으로 저장하지 않고 이유를 알린다", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "dpr-1", "DOM 분할 로직은 DPR과 무관하다");
  await openFixture(page);
  await chooseZoom(page, 0.5); // 1쪽과 2쪽이 함께 그려지는 확대
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
    document.getSelection()!.removeAllRanges();
    document.getSelection()!.addRange(range);
  }, start);

  await expect(page.locator(".quad-overlay")).toHaveCount(2);
  await expect(page.locator(SELECTION_STATUS)).toHaveText("여러 쪽에 걸친 선택은 주석으로 저장할 수 없습니다. 쪽마다 따로 선택하세요.");
  const menu = page.getByRole("menu", { name: "고른 글로 할 일" });
  await expect(menu).toContainText("한 쪽 안에서 고르세요");
  await expect(menu.getByRole("menuitem")).toHaveCount(0);
});

test("R14 첨자가 섞인 선택은 원문 인용과 추정 표기를 따로 보이고 저장한다", async ({ page }) => {
  const fixture = await uploadPdf(page, SUBSCRIPTS_PDF, "subscripts.pdf");
  await clearAnnotations(page, fixture.versionId);
  await openFixture(page, SUBSCRIPTS_PDF, "subscripts.pdf");
  const status = page.locator(SELECTION_STATUS);

  const seen: Record<string, { quote: string; display: string | null }> = {};
  for (const line of SUBSCRIPTS.lines) {
    await selectLine(page, line.v_range);
    // 원문 인용은 추출된 그대로다: 첨자 기호 없이 같은 글자들 (공백은 PDF.js가 정한다).
    await expect.poll(async () => withoutSpaces(await status.getAttribute("data-quote"))).toBe(withoutSpaces(line.text));
    if (line.display_quote) {
      await expect(status).toHaveAttribute("data-display-quote", line.display_quote);
      await expect(status).toContainText(`(추정 표기: ${line.display_quote})`);
    } else {
      await expect(status).not.toHaveAttribute("data-display-quote");
    }
    seen[line.name] = { quote: (await status.getAttribute("data-quote"))!, display: await status.getAttribute("data-display-quote") };
  }

  const stacked = SUBSCRIPTS.lines[0];
  await selectLine(page, stacked.v_range);
  await expect(status).toHaveAttribute("data-display-quote", stacked.display_quote!);
  await saveSelection(page, "");
  await openPanel(page, "주석");
  const anchorId = (await page.locator(NOTES).getAttribute("data-anchor-id"))!;
  const anchor = await (await page.request.get(`/api/v1/anchors/${anchorId}`)).json();
  expect(anchor.display_quote).toBe(stacked.display_quote);
  expect(withoutSpaces(anchor.quote)).toBe(withoutSpaces(stacked.text));
  expect(anchor.quote).not.toMatch(/[_^{}]/);
  await expect(page.locator(`${NOTES} .display-quote code`)).toHaveText(stacked.display_quote!);
  await expect(page.locator(`${NOTES} .display-quote .badge`)).toHaveText("추정");
  console.log(`W04 subscripts ${JSON.stringify(seen)}`);
});

/** 1쪽 첫 표식 둘레에 원문 위치와 주석을 API로 만든다. */
async function createAnchorViaApi(page: Page, versionId: string, comment: string): Promise<string> {
  const [u, v] = EXPECTED.pages[0].markers[0].normalized;
  const quad = [u, v - 0.02, u + 0.3, v - 0.02, u + 0.3, v + 0.005, u, v + 0.005];
  const anchor = await page.request.post("/api/v1/anchors", {
    data: {
      schema_version: "anchor.v1",
      version_id: versionId,
      page_index: 0,
      quads: [quad],
      quote: EXPECTED.pages[0].markers[0].text,
    },
  });
  expect(anchor.status()).toBe(201);
  const { anchor_id } = await anchor.json();
  expect((await page.request.post("/api/v1/annotations", { data: { anchor_id, comment } })).status()).toBe(201);
  return anchor_id;
}

/** 고른 글 곁의 메뉴에서 "주석"을 눌러 메모 창에서 저장한다. */
async function saveSelection(page: Page, comment: string) {
  // 메뉴는 고른 글이 화면에 있을 때만 보인다. 큰 쪽(UserUnit 2)은 쪽을 가운데 두어도 표식이 화면 밖일 수 있다.
  await page.locator(".quad-overlay .quad-mark").first().scrollIntoViewIfNeeded();
  await menuItem(page, "주석").click();
  await saveNote(page, comment);
}

/** 1쪽에서 세로 범위(정규화 v)에 가운데가 들어오는 text layer span들을 처음부터 끝까지 선택한다. */
async function selectLine(page: Page, vRange: [number, number]) {
  await expect(page.locator('.page[data-page-number="1"] .textLayer:not([hidden]) span').first()).toBeVisible();
  await page.evaluate(([v0, v1]) => {
    const pageDiv = document.querySelector('.page[data-page-number="1"]')!;
    const frame = pageDiv.getBoundingClientRect();
    const spans = [...pageDiv.querySelectorAll(".textLayer span")].filter((span) => {
      const rect = span.getBoundingClientRect();
      const v = ((rect.top + rect.bottom) / 2 - frame.top) / frame.height;
      return rect.height > 0 && span.firstChild instanceof Text && v >= v0 && v <= v1;
    });
    if (spans.length === 0) throw new Error(`줄의 span을 찾지 못함: ${v0}–${v1}`);
    const range = document.createRange();
    range.setStart(spans[0].firstChild!, 0);
    const last = spans.at(-1)!.firstChild!;
    range.setEnd(last, last.textContent!.length);
    document.getSelection()!.removeAllRanges();
    document.getSelection()!.addRange(range);
  }, vRange);
}

async function isInsideScroller(page: Page, mark: Locator): Promise<boolean> {
  const box = await mark.boundingBox();
  const view = await page.locator(".reader-scroll").boundingBox();
  if (!box || !view) return false;
  return box.x >= view.x && box.y >= view.y && box.x + box.width <= view.x + view.width && box.y + box.height <= view.y + view.height;
}

async function expectPath(page: Page, pathAndQuery: string) {
  await expect.poll(() => {
    const url = new URL(page.url());
    return url.pathname + url.search;
  }).toBe(pathAndQuery);
}

function withoutSpaces(text: string | null): string {
  return (text ?? "").replace(/\s/g, "");
}
