/**
 * U4 탐색 (2026-10-02, UI_PLAN §5 U4, IMPL §10.8, 사용자 결정 D5·D6).
 * - 목차 패널: PDF 목차(outline, text-navigation.pdf), 없으면 본문 제목(text-references.pdf), 둘 다 없으면 안내
 *   (text-mixed.pdf), 쪽 미리보기(보이는 쪽만 그림). Ctrl+Shift+O로 열고 닫고, 연 상태를 기억한다.
 * - 본문 찾기: Ctrl+F(브라우저 찾기 대신), 개수·위치, Enter·Shift+Enter, Esc. 찾기 강조가 있어도 참고문헌 번호를 따라간다.
 * - 논문 정보: DOI(본문 추출이 찾음), 쪽·추출 상태, 제목·저자·연도 고치기.
 */
import { readFileSync } from "node:fs";

import { expect, type Locator, type Page, test } from "@playwright/test";

import { chooseZoom, FIXTURE_DIR, openFixture, uploadPdf } from "./fixture";

type Outline = [string, number, number, number][];
const EXPECTED = JSON.parse(readFileSync(new URL("text-extraction.json", FIXTURE_DIR), "utf-8")).documents;
const NAVIGATION = EXPECTED["text-navigation.pdf"] as { outline: Outline; doi: string };
const REFERENCES = EXPECTED["text-references.pdf"] as { headings: [string, number, number][] };

function pdf(file: string): Buffer {
  return readFileSync(new URL(file, FIXTURE_DIR));
}

/** 올리고 본문 추출이 끝나기를 기다린다(본문 제목·DOI·참고문헌 쪽이 추출 결과에서 나온다). */
async function uploadExtracted(page: Page, file: string) {
  const uploaded = await uploadPdf(page, pdf(file), file);
  await expect
    .poll(async () => (await (await page.request.get(`/api/v1/versions/${uploaded.versionId}/pages`)).json()).status, { timeout: 30_000 })
    .toMatch(/^(INDEXED|PARTIAL|FAILED)$/);
  return uploaded;
}

async function openExtracted(page: Page, file: string) {
  const uploaded = await uploadExtracted(page, file);
  await openFixture(page, pdf(file), file);
  return uploaded;
}

function toc(page: Page): Locator {
  return page.getByRole("complementary", { name: "논문 목차" });
}

/** 항목: [제목, 단계, 쪽(1부터)] */
function entriesOf(panel: Locator) {
  return panel.locator(".toc-entry").evaluateAll((elements) =>
    elements.map((element) => [
      element.querySelector(".toc-entry-title")!.textContent,
      Number((element as HTMLElement).dataset.level),
      Number(element.querySelector(".toc-entry-page")!.textContent),
    ]),
  );
}

/** 글 조각이 스크롤 영역 위에서 얼마나 떨어져 있는지(px). 보이지 않으면 null */
async function offsetFromTop(page: Page, target: Locator) {
  const [box, scroller] = await Promise.all([target.boundingBox(), page.locator(".reader-scroll").boundingBox()]);
  if (!box || !scroller || box.y + box.height < scroller.y || box.y > scroller.y + scroller.height) return null;
  return box.y - scroller.y;
}

function textSpan(page: Page, pageNumber: number, text: string) {
  return page.locator(`.page[data-page-number="${pageNumber}"] .textLayer span`, { hasText: text }).first();
}

/** 조각 안 needle 글자들의 화면 가운데. 찾기 강조가 조각을 여러 글 노드로 나눠도 찾는다. */
async function textCenter(target: Locator, needle: string) {
  await target.scrollIntoViewIfNeeded();
  return target.evaluate((element, needle) => {
    const walker = document.createTreeWalker(element, NodeFilter.SHOW_TEXT);
    const nodes: Text[] = [];
    while (walker.nextNode()) nodes.push(walker.currentNode as Text);
    const start = nodes.map((node) => node.data).join("").indexOf(needle);
    const end = start + needle.length;
    const range = document.createRange();
    let offset = 0;
    for (const node of nodes) {
      const next = offset + node.length;
      if (start >= offset && start < next) range.setStart(node, start - offset);
      if (end > offset && end <= next) {
        range.setEnd(node, end - offset);
        break;
      }
      offset = next;
    }
    const rect = range.getBoundingClientRect();
    return { x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 };
  }, needle);
}

test("목차: PDF 목차를 단계대로 보이고 누르면 그 목적지로 간다. Ctrl+Shift+O로 열고 닫고, 연 상태를 기억한다", async ({ page }) => {
  await openExtracted(page, "text-navigation.pdf");
  await expect(toc(page)).toHaveCount(0); // 처음은 닫힘
  await page.keyboard.press("Control+Shift+KeyO");
  await expect(toc(page)).toBeVisible();
  await expect(page.getByRole("button", { name: "논문 목차" })).toHaveAttribute("aria-pressed", "true");

  // PDF 목차 그대로(본문 제목 "2.1 Setup"이 아니라 outline의 "2.1 Experimental setup")
  await expect.poll(() => entriesOf(toc(page))).toEqual(NAVIGATION.outline.map(([title, pageIndex, level]) => [title, level, pageIndex + 1]));
  await expect(toc(page).locator(".toc-foot")).toHaveText("PDF 목차(outline)에서 읽음");

  // 목적지(2쪽 가운데 /XYZ 위쪽 412)가 스크롤 영역 위쪽 3분의 1에 온다(본문 제목·링크와 같은 줄). 지금 항목이 강조된다
  await toc(page).getByRole("button", { name: /2\.1 Experimental setup/ }).click();
  await expect(page.locator(".page-box")).toHaveAttribute("data-page", "2");
  const third = (await page.locator(".reader-scroll").evaluate((element) => element.clientHeight)) / 3;
  await expect.poll(() => offsetFromTop(page, textSpan(page, 2, "2.1 Setup")), { message: "목적지가 위쪽 3분의 1에" }).toBeGreaterThanOrEqual(third - 2);
  expect(await offsetFromTop(page, textSpan(page, 2, "2.1 Setup"))).toBeLessThan(third + 60);
  await expect(toc(page).locator('.toc-entry[aria-current="location"]')).toContainText("2.1 Experimental setup");
  await toc(page).getByRole("button", { name: /2\.2 Results/ }).click();
  await expect(page.locator(".page-box")).toHaveAttribute("data-page", "3");
  await expect(toc(page).locator('.toc-entry[aria-current="location"]')).toContainText("2.2 Results");

  // 목적지가 배율을 바꾸지 않는다
  await chooseZoom(page, 1.5);
  await toc(page).getByRole("button", { name: /1 Introduction/ }).click();
  await expect(page.locator(".page-box")).toHaveAttribute("data-page", "1");
  await expect(page.getByRole("button", { name: "배율", exact: true })).toHaveAttribute("data-zoom", "1.5");

  // 연 상태를 기억한다. 단축키·단추로 닫고 연다
  await page.reload();
  await expect(toc(page)).toBeVisible();
  await page.keyboard.press("Control+Shift+KeyO");
  await expect(toc(page)).toHaveCount(0);
  await page.getByRole("button", { name: "논문 목차" }).click();
  await expect(toc(page)).toBeVisible();
});

/**
 * 2026-10-03 사용자 확인: 한 쪽에 5.2와 5.2.1이 있으면 5.2를 눌러도 5.2.1이 강조됐다(지금 항목을 쪽 단위로만 골라 같은 쪽의 뒤 항목).
 * 지금 항목은 읽는 줄(스크롤 영역 위쪽 3분의 1) 위의 마지막 항목이고, 누른 항목은 스크롤하기 전까지 그대로다.
 */
test("목차의 지금 항목: 한 쪽에 제목이 둘이면 누른 제목이 강조되고, 스크롤하면 읽는 줄을 지난 제목으로 바뀐다", async ({ page }) => {
  const current = () => toc(page).locator('.toc-entry[aria-current="location"] .toc-entry-title');
  const scrollBy = (dy: number) => page.locator(".reader-scroll").evaluate((element, dy) => element.scrollBy(0, dy), dy);
  const third = async () => (await page.locator(".reader-scroll").evaluate((element) => element.clientHeight)) / 3;

  // PDF 목차: 2쪽의 "2 Method"(위)와 "2.1 Experimental setup"(가운데)
  await openExtracted(page, "text-navigation.pdf");
  await page.getByRole("button", { name: "논문 목차" }).click();
  await toc(page).getByRole("button", { name: /^2 Method/ }).click();
  await expect(current()).toHaveText("2 Method");
  await page.waitForTimeout(300); // 다시 고르는 스크롤 사건이 지나도 그대로다
  await expect(current()).toHaveText("2 Method");
  // 2.1 줄이 읽는 줄을 지나도록 내리면 2.1, 다시 그 위로 올리면 2 Method
  const below = (await offsetFromTop(page, textSpan(page, 2, "2.1 Setup")))!;
  await scrollBy(below - (await third()) + 20);
  await expect(current()).toHaveText("2.1 Experimental setup");
  await scrollBy(-60);
  await expect(current()).toHaveText("2 Method");

  // 본문 제목(사용자 논문과 같은 경우): 2쪽의 "2 Method"와 "References"
  await openExtracted(page, "text-references.pdf");
  await toc(page).getByRole("button", { name: /^2 Method/ }).click();
  await expect(current()).toHaveText("2 Method");
  await toc(page).getByRole("button", { name: /References/ }).click();
  await expect(current()).toHaveText("References");
  // 문서 끝 쪽 제목은 읽는 줄까지 올라오지 못할 수 있다(50%면 마지막 쪽 맨 위가 끝까지 내려도 읽는 줄 아래). 누른 제목이 그대로 강조된다
  await chooseZoom(page, 0.5);
  await toc(page).getByRole("button", { name: /A Appendix/ }).click();
  await expect(page.locator(".page-box")).toHaveAttribute("data-page", "4");
  await page.waitForTimeout(300);
  await expect(current()).toHaveText("A Appendix");
});

test("목차: PDF 목차가 없으면 본문 제목으로 만들고, 그것도 없으면 알린다", async ({ page }) => {
  await uploadExtracted(page, "text-mixed.pdf");
  await openExtracted(page, "text-references.pdf");
  await page.getByRole("button", { name: "논문 목차" }).click();
  await expect.poll(() => entriesOf(toc(page))).toEqual(REFERENCES.headings.map(([title, pageIndex, level]) => [title, level, pageIndex + 1]));
  await expect(toc(page).locator(".toc-foot")).toHaveText("PDF에 목차가 없어 본문 제목에서 찾음");

  // 본문 제목 줄로 간다(스크롤 영역 위쪽 3분의 1)
  await toc(page).getByRole("button", { name: /References/ }).click();
  await expect.poll(() => offsetFromTop(page, textSpan(page, 2, "References"))).not.toBeNull();
  const scroller = (await page.locator(".reader-scroll").boundingBox())!;
  expect(await offsetFromTop(page, textSpan(page, 2, "References"))).toBeLessThan(scroller.height / 2);
  await expect(toc(page).locator('.toc-entry[aria-current="location"]')).toContainText("References");

  // PDF 목차도 본문 제목도 없는 문서 (서재 줄의 제목을 눌러 연다)
  const mixed = await uploadPdf(page, pdf("text-mixed.pdf"), "text-mixed.pdf");
  await page.goto("/");
  await page.locator(`tr[data-paper-id="${mixed.paperId}"] .paper-open`).click();
  await expect(toc(page).locator(".toc-message")).toHaveText(/PDF에 목차가 없고 본문 제목도 찾지 못했습니다/);
});

test("쪽 미리보기: 목록에서 보이는 쪽만 그리고, 지금 쪽을 표시하며, 누르면 그 쪽으로 간다", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 600 }); // 마지막 쪽 미리보기가 목록 밖에 있도록
  await openExtracted(page, "text-digital.pdf");
  await page.keyboard.press("Control+Shift+KeyO");
  await toc(page).locator('label[title="쪽 미리보기"]').click();
  const thumbs = toc(page).locator(".toc-thumb");
  await expect(thumbs).toHaveCount(6);
  await expect(thumbs.first()).toHaveAttribute("data-drawn", "true");
  await expect(thumbs.first()).toHaveAttribute("aria-current", "page");
  // 그린 미리보기에 글자가 있다(빈 칸이 아니다)
  const inked = await thumbs.first().locator("canvas").evaluate((canvas: HTMLCanvasElement) => {
    const data = canvas.getContext("2d")!.getImageData(0, 0, canvas.width, canvas.height).data;
    let dark = 0;
    for (let index = 0; index < data.length; index += 4) if (data[index] < 200 && data[index + 3] > 0) dark++; // 작게 그린 글자는 회색이다
    return dark;
  });
  expect(inked).toBeGreaterThan(50);

  // 마지막 쪽은 목록을 내려야 그린다
  await expect(thumbs.last()).toHaveAttribute("data-drawn", "false");
  await thumbs.last().scrollIntoViewIfNeeded();
  await expect(thumbs.last()).toHaveAttribute("data-drawn", "true");

  await thumbs.nth(1).click();
  await expect(page.locator(".page-box")).toHaveAttribute("data-page", "2");
  await expect(thumbs.nth(1)).toHaveAttribute("aria-current", "page");
});

test("본문 찾기: Ctrl+F로 열어 개수와 위치를 보이고, Enter·Shift+Enter로 오가며, Esc로 닫으면 강조가 사라진다", async ({ page }) => {
  await openExtracted(page, "text-references.pdf");
  await page.evaluate(() => {
    window.addEventListener("keydown", (event) => {
      if (event.code === "KeyF") (window as unknown as { ctrlF: boolean }).ctrlF = event.defaultPrevented;
    });
  });
  await page.keyboard.press("Control+KeyF");
  const bar = page.getByRole("search", { name: "본문에서 찾기" });
  const input = bar.getByLabel("찾을 말");
  await expect(bar).toBeVisible();
  await expect(input).toBeFocused();
  expect(await page.evaluate(() => (window as unknown as { ctrlF: boolean }).ctrlF), "브라우저 찾기 대신").toBe(true);

  // "cache": 1쪽 둘, 2쪽 둘, 3쪽 하나(caches)
  await page.keyboard.type("cache");
  const count = bar.locator(".find-count");
  const selected = (pageNumber: number) => page.locator(`.page[data-page-number="${pageNumber}"] .textLayer .highlight.selected`);
  await expect(count).toHaveText("1 / 5");
  await expect(selected(1)).toHaveCount(1);
  await page.keyboard.press("Enter");
  await page.keyboard.press("Enter");
  await expect(count).toHaveText("3 / 5");
  await expect(selected(2)).toHaveCount(1);
  await page.keyboard.press("Shift+Enter");
  await expect(count).toHaveText("2 / 5");
  await expect(selected(1)).toHaveCount(1);
  for (let step = 0; step < 4; step++) await bar.getByRole("button", { name: "다음 찾기" }).click();
  await expect(count).toHaveText("1 / 5"); // 끝에서 처음으로

  await input.fill("zzqq");
  await expect(count).toHaveText("없음");

  // 찾기 강조가 조각을 나눠도 Ctrl+클릭한 참고문헌 번호를 따라간다
  await input.fill("Prior");
  await expect(count).toHaveText("1 / 1");
  const point = await textCenter(textSpan(page, 1, "Prior"), "[2]");
  await page.keyboard.down("Control");
  await page.mouse.click(point.x, point.y);
  await page.keyboard.up("Control");
  await expect(page.locator('.page[data-page-number="2"] > .annotation-overlay > .quad-mark.is-focused')).toHaveCount(1);

  // Esc로 닫으면 강조가 사라지고 본문으로 포커스가 온다. 머리 단추로도 연다
  await input.press("Escape");
  await expect(bar).toHaveCount(0);
  await expect(page.locator(".textLayer .highlight")).toHaveCount(0);
  await expect(page.locator(".reader-scroll")).toBeFocused();
  await page.getByRole("button", { name: "본문에서 찾기" }).click();
  await expect(bar).toBeVisible();
});

test("논문 정보: DOI·쪽·추출 상태를 보이고, 제목·저자·연도를 고치면 머리 제목이 바뀌고 다시 열어도 남는다", async ({ page }) => {
  const { paperId } = await uploadExtracted(page, "text-navigation.pdf");
  // E2E 데이터 폴더는 실행 사이에 남는다. 처음 값으로 되돌린다(DOI 자동 찾기는 pytest가 본다)
  const original = { title: "Paperloom text fixture navigation (synthetic)", authors: [], year: null, doi: NAVIGATION.doi };
  expect((await page.request.put(`/api/v1/papers/${paperId}/metadata`, { data: original })).status()).toBe(200);
  await openFixture(page, pdf("text-navigation.pdf"), "text-navigation.pdf");

  await page.getByRole("button", { name: "논문 정보" }).click();
  const info = page.getByRole("dialog", { name: "논문 정보" });
  await expect(info).toContainText(original.title);
  await expect(info.getByRole("link", { name: NAVIGATION.doi })).toHaveAttribute("href", `https://doi.org/${NAVIGATION.doi}`);
  await expect(info).toContainText("4쪽");
  await expect(info).toContainText("정상 · 참고문헌 4쪽");
  await expect(info).toContainText("KB · ");

  await info.getByRole("button", { name: "고치기" }).click();
  await info.getByLabel("제목").fill("Navigation Study");
  await info.getByLabel(/저자/).fill("Jun Xiao\n\nAndy D. Pimentel");
  await info.getByLabel("연도").fill("22");
  await info.getByRole("button", { name: "저장" }).click();
  await expect(info).toContainText("연도는 1000–2100의 네 자리 숫자입니다.");
  await info.getByLabel("연도").fill("2022");
  await info.getByRole("button", { name: "저장" }).click();
  await expect(info).toContainText("Jun Xiao, Andy D. Pimentel");
  await expect(info).toContainText("2022");
  await expect(page.locator(".reader-title")).toHaveText("Navigation Study");

  await page.keyboard.press("Escape");
  await expect(info).toHaveCount(0);
  await page.reload();
  await expect(page.locator(".reader-title")).toHaveText("Navigation Study");
  const saved = await (await page.request.get(`/api/v1/papers/${paperId}`)).json();
  expect([saved.title, saved.authors, saved.year, saved.doi]).toEqual(["Navigation Study", ["Jun Xiao", "Andy D. Pimentel"], 2022, NAVIGATION.doi]);
});
