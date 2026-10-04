/**
 * U7 쪽 번역 (docs/UI_PLAN.md U7, 사용자 결정 D3·D9·D10·D11, 시안 Reader v3·Translation Tab).
 * 번역 보기를 켜면 지금 쪽을 바로 번역한다. 저장된 쪽은 다시 번역하지 않는다. 사용자가 시작하면 모든 쪽(참고문헌 제외)을
 * 한 쪽씩 번역한다. 번역문의 문장에 마우스를 올리면 원문 쪽의 그 문장을 강조한다(2026-10-03 사용자 요청).
 * 가짜 CLI(tests/fixtures/fake_claude)는 문장마다 "[번역] 원문"으로 옮긴다(원문의 <b>·<i> 표시도 그대로). 합성 fixture
 * text-navigation.pdf(4쪽, 4쪽은 참고문헌), text-styles.pdf(굵게·기울임·글꼴 크기), figures.pdf(그림 안 글자).
 */
import { readFileSync } from "node:fs";

import { expect, type Page, test } from "@playwright/test";

import { fakeRuns, FIXTURE_DIR, uploadPdf } from "./fixture";

const FILE = "text-navigation.pdf";
const DEFAULTS = {
  answer_language: "ko",
  default_model: "sonnet",
  paper_text_chars: 120000,
  theme: "system",
  font_size: 14,
  translation_font_size: null,
  math_delimiters: "dollar",
  prompts: { system: "", explain: "", translate: "", summary: "" },
};

/** 본문을 추출한 논문을 올리고, 앞 실행이 남긴 번역과 설정을 지운다 */
async function prepare(page: Page, file = FILE) {
  const uploaded = await uploadPdf(page, readFileSync(new URL(file, FIXTURE_DIR)), file);
  await expect
    .poll(async () => (await (await page.request.get(`/api/v1/versions/${uploaded.versionId}/pages`)).json()).status, { timeout: 30_000 })
    .toMatch(/^(INDEXED|PARTIAL)$/);
  expect((await page.request.delete(`/api/v1/versions/${uploaded.versionId}/translations/ko`)).status()).toBe(204);
  // 추출기 버전이 바뀐 뒤 처음 실행하면 서버가 시작할 때 이미 올린 논문을 다시 추출한다(그동안은 409 TEXT_NOT_READY)
  await expect
    .poll(async () => (await page.request.get(`/api/v1/versions/${uploaded.versionId}/pages/0/translations/ko`)).status(), { timeout: 30_000 })
    .toBe(404);
  expect((await page.request.put("/api/v1/settings", { data: DEFAULTS })).status()).toBe(200);
  return uploaded;
}

async function openReader(page: Page, { paperId, versionId }: { paperId: string; versionId: string }) {
  await page.goto(`/reader/${paperId}?version=${versionId}`);
  await expect(page.locator('.page[data-page-number="1"] .textLayer span').first()).toBeAttached();
}

/** 쪽 번역 차례로 가짜 CLI가 받은 실행들 (쪽마다 하나) */
function translationRuns() {
  return fakeRuns().filter((run) => run.message.message.content.some((block) => block.text?.includes("## 번역할 쪽 (JSON)")));
}

const translated = (page: Page, index: number) => page.locator(`.translated-page[data-page-index="${index}"]`);

async function goToPage(page: Page, pageNumber: number) {
  await page.getByLabel("쪽 번호").fill(String(pageNumber));
  await page.getByLabel("쪽 번호").press("Enter");
  await expect(page.locator(".page-box")).toHaveAttribute("data-page", String(pageNumber));
}

/** text layer에서 그 글이 그려진 화면 사각형 */
async function textRect(page: Page, pageNumber: number, needle: string) {
  return page.locator(`.page[data-page-number="${pageNumber}"] .textLayer`).evaluate((layer, needle) => {
    const walker = document.createTreeWalker(layer, NodeFilter.SHOW_TEXT);
    const nodes: Text[] = [];
    while (walker.nextNode()) nodes.push(walker.currentNode as Text);
    const joined = nodes.map((node) => node.data).join("");
    const start = joined.indexOf(needle);
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
    return { left: rect.left, right: rect.right, top: rect.top, bottom: rect.bottom };
  }, needle);
}

test.afterEach(async ({ page }) => {
  await page.request.put("/api/v1/settings", { data: DEFAULTS });
});

test("레이아웃 유지: 켜면 지금 쪽을 바로 번역해 원문 옆 같은 자리에 두고, 문장에 마우스를 올리면 원문 문장을 강조한다", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "dpr-1", "번역 흐름은 DPR과 무관하다");
  const uploaded = await prepare(page);
  await openReader(page, uploaded);
  const before = translationRuns().length;

  // 1) 켜면 지금 쪽(1쪽)을 바로 번역한다(D10). 번역 쪽은 원문 쪽 오른쪽, 같은 높이·크기
  const toggle = page.getByRole("button", { name: "쪽 번역", exact: true });
  await toggle.click();
  await expect(toggle).toHaveAttribute("aria-pressed", "true");
  await expect(translated(page, 0).locator(".translated-block").first()).toHaveText("[번역] Paperloom Navigation Sample", { timeout: 15_000 });
  await expect(page.locator(".translation-bar .translation-bar-status")).toHaveText("번역함 · sonnet");
  await expect(page.locator(".translation-bar")).toContainText("1쪽 번역 · 한국어");
  expect(translationRuns().length).toBe(before + 1);
  const original = (await page.locator('.page[data-page-number="1"]').boundingBox())!;
  const copy = (await translated(page, 0).boundingBox())!;
  expect(copy.x).toBeGreaterThan(original.x + original.width);
  expect(Math.abs(copy.y - original.y)).toBeLessThan(3);
  expect(Math.abs(copy.width - original.width)).toBeLessThan(3);
  // 영역 설명(영역 모드)을 켜고 꺼도 원문 쪽은 번역 쪽 왼쪽에 그대로다 (2026-10-03 사용자 확인: 원문이 번역 쪽 아래로 밀렸다)
  const regionMode = page.getByRole("button", { name: "영역 설명" });
  for (let toggled = 0; toggled < 2; toggled++) {
    await regionMode.click();
    await expect(regionMode).toHaveAttribute("aria-pressed", toggled === 0 ? "true" : "false");
    const shifted = (await page.locator('.page[data-page-number="1"]').boundingBox())!;
    expect(shifted.x).toBeCloseTo(original.x, 0);
    expect((await translated(page, 0).boundingBox())!.x).toBeGreaterThan(shifted.x + shifted.width);
  }
  // 번역문은 원문 문단 자리에 있다(제목 줄과 같은 높이)
  const title = await textRect(page, 1, "Paperloom Navigation Sample");
  const titleBox = (await translated(page, 0).locator(".translated-block").first().boundingBox())!;
  expect(Math.abs(titleBox.y - title.top)).toBeLessThan(6);
  expect(Math.abs(titleBox.x - copy.x - (title.left - original.x))).toBeLessThan(6);

  // 2) 번역 문장에 마우스를 올리면 원문의 그 문장을 강조하고, 떼면 지운다
  await translated(page, 0).locator(".translated-sentence", { hasText: "[번역] Section one" }).hover();
  const marks = page.locator('.page[data-page-number="1"] .source-overlay .quad-mark');
  await expect(marks).toHaveCount(1);
  const mark = (await marks.boundingBox())!;
  const sentence = await textRect(page, 1, "Section one introduces the cache model.");
  expect(Math.abs(mark.x - sentence.left)).toBeLessThan(3);
  expect(Math.abs(mark.x + mark.width - sentence.right)).toBeLessThan(3);
  expect(Math.abs(mark.y - sentence.top)).toBeLessThan(4);
  await page.mouse.move(5, 5);
  await expect(marks).toHaveCount(0);

  // 2b) 반대로 원문 문장에 마우스를 올리면 그 번역 문장(과 원문 문장)을 강조하고, 원문을 벗어나면 지운다 (2026-10-04 사용자 요청).
  // 한 문단의 두 문장 가운데 마우스 아래 문장이다(둘째 문장은 둘째 줄 가운데에서 시작한다)
  const linkedSentence = translated(page, 0).locator(".translated-sentence.is-linked");
  const hoverText = async (needle: string) => {
    const rect = await textRect(page, 1, needle);
    await page.mouse.move((rect.left + rect.right) / 2, (rect.top + rect.bottom) / 2);
  };
  await hoverText("Section one introduces the cache model.");
  await expect(linkedSentence).toHaveCount(1);
  await expect(linkedSentence).toContainText("[번역] Section one introduces the cache model.");
  await expect(marks).toHaveCount(1);
  await hoverText("Navigation fixture text");
  await expect(linkedSentence).toContainText("[번역] Navigation fixture text");
  // 원문에서 곧바로 번역 문장으로 옮기면 번역 → 원문 강조가 남는다(원문을 벗어나며 지우는 것은 원문 위에서 그린 강조뿐)
  await translated(page, 0).locator(".translated-sentence", { hasText: "[번역] Section one" }).hover();
  await expect(linkedSentence).toHaveCount(0);
  await page.waitForTimeout(100);
  await expect(marks).toHaveCount(1);
  await page.mouse.move(5, 5);
  await expect(linkedSentence).toHaveCount(0);
  await expect(marks).toHaveCount(0);

  // 3) 쪽을 옮기면 그 쪽을 번역한다
  await goToPage(page, 2);
  await expect(translated(page, 1).locator(".translated-block").first()).toHaveText("[번역] 2 Method", { timeout: 15_000 });
  expect(translationRuns().length).toBe(before + 2);

  // 4) 새로고침해도 켬·보기 방식을 기억하고, 저장된 쪽은 다시 번역하지 않는다(D3)
  await page.reload();
  await expect(page.getByRole("button", { name: "쪽 번역", exact: true })).toHaveAttribute("aria-pressed", "true");
  await expect(translated(page, 0).locator(".translated-block").first()).toHaveText("[번역] Paperloom Navigation Sample");
  await page.waitForTimeout(500);
  expect(translationRuns().length).toBe(before + 2);

  // 5) 다시 번역은 실행한다
  await page.getByRole("button", { name: "다시 번역" }).click();
  await expect.poll(() => translationRuns().length).toBe(before + 3);
  await expect(page.locator(".translation-bar .translation-bar-status")).toHaveText("번역함 · sonnet");
});

test.describe("Windows 화면 배율 125%", () => {
  test.use({ deviceScaleFactor: 1.25 });

  test("레이아웃 유지: 확대해도 번역 쪽이 원문 쪽과 같은 자리·같은 크기다", async ({ page }, testInfo) => {
    // 2026-10-04 사용자 확인: 100%에서는 맞는데 확대하면 쪽이 어긋났다. PDF.js는 쪽을 그릴 때 쪽 크기를 화면 픽셀 단위
    // (배율 1.25면 4px)로 내린다. 번역 쪽은 내리지 않은 크기였고, 그린 쪽이 줄어 아래 쪽들이 올라가도 다시 재지 않았다.
    test.skip(testInfo.project.name !== "dpr-1", "화면 배율은 이 시험이 정한다");
    const uploaded = await prepare(page);
    await openReader(page, uploaded);
    await page.getByRole("button", { name: "쪽 번역", exact: true }).click();
    await expect(translated(page, 0).locator(".translated-block").first()).toBeVisible({ timeout: 15_000 });
    await page.getByRole("button", { name: "확대" }).click();
    await page.getByRole("button", { name: "확대" }).click();
    /** 쪽마다 번역 쪽과 원문 쪽의 위치·크기 차이(px) 가운데 가장 큰 것 */
    const worst = () =>
      page.evaluate(() =>
        Math.max(
          ...[...document.querySelectorAll<HTMLElement>(".translated-page")].map((slot) => {
            const original = document.querySelector(`.page[data-page-number="${Number(slot.dataset.pageIndex) + 1}"]`)!;
            const [a, b] = [original.getBoundingClientRect(), slot.getBoundingClientRect()];
            return Math.max(Math.abs(a.top - b.top), Math.abs(a.height - b.height), Math.abs(a.width - b.width));
          }),
        ),
      );
    await expect.poll(worst).toBeLessThan(0.5);
    // 아래 쪽들을 그려도(쪽 크기가 내려진다) 그대로 맞는다
    await page.locator(".reader-scroll").evaluate((element) => element.scrollTo(0, element.scrollHeight));
    await expect(page.locator('.page[data-page-number="4"] canvas')).toBeAttached();
    await expect.poll(worst).toBeLessThan(0.5);
  });
});

/** 레이아웃 유지 번역 쪽의 배율(쪽 내용의 viewport 폭 / PDF 폭). 쪽 상자는 원문 쪽처럼 화면 픽셀 단위로 내려져 조금 작을 수 있다 */
const layoutScale = (page: Page, index = 0) =>
  translated(page, index)
    .locator(".translated-page-content")
    .evaluate((element) => parseFloat(getComputedStyle(element).width) / 612);

/** 요소의 계산된 글꼴 크기·줄 간격(px) */
async function fontOf(locator: ReturnType<Page["locator"]>) {
  return locator.evaluate((element) => {
    const style = getComputedStyle(element);
    return { size: parseFloat(style.fontSize), lineHeight: parseFloat(style.lineHeight) };
  });
}

test("레이아웃 유지: 원문의 글꼴 크기·줄 간격·굵게·기울임을 따르고, 글꼴 단추는 원문 크기 배율을 바꾼다", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "dpr-1", "번역 흐름은 DPR과 무관하다");
  const uploaded = await prepare(page, "text-styles.pdf");
  await openReader(page, uploaded);
  await page.getByRole("button", { name: "쪽 번역", exact: true }).click();
  const [heading, body] = [translated(page, 0).locator(".translated-block").nth(0), translated(page, 0).locator(".translated-block").nth(1)];
  await expect(heading).toHaveText("[번역] 3 Styled Section", { timeout: 15_000 });
  // 브리지는 원문의 굵게·기울임을 <b>·<i> 표시로 보낸다
  const sent = JSON.stringify(translationRuns().at(-1)!.message);
  expect(sent).toContain("<b>3 Styled Section</b>");
  expect(sent).toContain("<i>kappaword</i>");
  expect(sent).toContain("<b><i>lambdaword</i></b>");

  // 번역문도 같은 말이 굵게·기울임이다
  await expect(heading).toHaveClass(/is-bold/);
  await expect(body.locator("i", { hasText: "kappaword" })).toHaveCount(1);
  await expect(body.locator("b", { hasText: "Bold lead in." })).toHaveCount(1);
  await expect(body.locator("b > i", { hasText: "lambdaword" })).toHaveCount(1);
  await expect(body.locator("b")).toHaveCount(2);
  // 인라인 수식의 위·아래첨자도 지킨다 (2026-10-04): 브리지가 <sup>·<sub>로 보내고 번역문이 위·아래첨자로 그린다
  expect(sent).toContain("t<sup>max</sup>");
  const inline = translated(page, 0).locator(".translated-block").nth(2);
  await expect(inline.locator("sup")).toHaveText(["max"]);
  await expect(inline.locator("sub")).toHaveText(["p", "k"]);

  // 글꼴 크기는 원문 pt × 쪽 배율(제목은 한 줄이라 그대로, 본문은 넘치지 않으면 그대로), 줄 간격은 원문 비율(12 / 10)
  const scale = await layoutScale(page);
  const headingFont = await fontOf(heading);
  expect(headingFont.size).toBeCloseTo(12 * scale, 0);
  const bodyFont = await fontOf(body);
  expect(bodyFont.size).toBeGreaterThan(10 * scale * 0.85);
  expect(bodyFont.size).toBeLessThanOrEqual(10 * scale + 0.01);
  expect(bodyFont.lineHeight / bodyFont.size).toBeCloseTo(1.2, 1);
  // 문단 상자는 원문 문단 자리(첫 줄 위 ~ 넷째 줄 아래)
  const first = await textRect(page, 1, "Styled fixture text keeps");
  const last = await textRect(page, 1, "words.");
  const original = (await page.locator('.page[data-page-number="1"]').boundingBox())!;
  const copy = (await translated(page, 0).boundingBox())!;
  const box = (await body.boundingBox())!;
  expect(Math.abs(box.y - first.top)).toBeLessThan(4 * scale);
  expect(Math.abs(box.y + box.height - last.bottom)).toBeLessThan(4 * scale);
  expect(Math.abs(box.x - copy.x - (first.left - original.x))).toBeLessThan(3);

  // 글꼴 단추: 레이아웃 유지에서는 원문 크기 배율(%). 작게 하면 번역문이 작아지고, 새로고침해도 기억한다
  const toolbar = page.locator(".translation-bar .translation-toolbar");
  await toolbar.getByRole("button", { name: "번역 글꼴 크기", exact: true }).click();
  await expect(toolbar.locator(".translation-font-value")).toHaveText("100%");
  await toolbar.getByRole("button", { name: "번역 글꼴 작게" }).click();
  await toolbar.getByRole("button", { name: "번역 글꼴 작게" }).click();
  await expect(toolbar.locator(".translation-font-value")).toHaveText("80%");
  await expect.poll(async () => (await fontOf(heading)).size).toBeCloseTo(12 * scale * 0.8, 0);
  await page.reload();
  await expect(heading).toHaveText("[번역] 3 Styled Section");
  const reloaded = await layoutScale(page); // 새로고침하면 배율이 다를 수 있다
  await expect.poll(async () => (await fontOf(heading)).size).toBeCloseTo(12 * reloaded * 0.8, 0);

  // 크게 하면 한 줄 제목은 그만큼 커지고, 넘치는 본문 문단은 원문 자리에 들어갈 만큼만 커진다(원문 여백을 지킨다)
  await toolbar.getByRole("button", { name: "번역 글꼴 크기", exact: true }).click();
  for (let step = 0; step < 5; step++) await toolbar.getByRole("button", { name: "번역 글꼴 크게" }).click();
  await expect(toolbar.locator(".translation-font-value")).toHaveText("130%");
  await expect(toolbar.getByRole("button", { name: "번역 글꼴 크게" })).toBeDisabled();
  await expect.poll(async () => (await fontOf(heading)).size).toBeCloseTo(12 * reloaded * 1.3, 0);
  expect((await fontOf(body)).size).toBeLessThan(10 * reloaded * 1.3 * 0.98);
  expect(await body.evaluate((element) => element.scrollHeight <= element.clientHeight + 1)).toBe(true);
});

test("그림 안 글자는 번역하지 않는다: 그림은 원문 그대로, 그림 설명·본문만 번역한다", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "dpr-1", "번역 흐름은 DPR과 무관하다");
  const uploaded = await prepare(page, "figures.pdf");
  await openReader(page, uploaded);
  await page.getByRole("button", { name: "쪽 번역", exact: true }).click();
  const blocks = translated(page, 0).locator(".translated-block");
  await expect(blocks).toHaveCount(2, { timeout: 15_000 });
  await expect(blocks).toContainText(["[번역] BODY TEXT THAT IS NOT A FIGURE", "[번역] Figure 1."]);
  await expect(translated(page, 0)).not.toContainText("Synthetic values");
  expect(JSON.stringify(translationRuns().at(-1)!.message)).not.toContain("Synthetic values");
});

test("본문만 번역한다: 머리글·바닥글, 따로 놓인 수식·식 번호(번호 없는 수식·수식 글꼴 수식 포함), 표 칸은 원문 그대로, 표 캡션은 번역한다", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "dpr-1", "번역 흐름은 DPR과 무관하다");
  const uploaded = await prepare(page, "text-parts.pdf");
  await openReader(page, uploaded);
  await page.getByRole("button", { name: "쪽 번역", exact: true }).click();
  const first = translated(page, 0).locator(".translated-block");
  await expect(first).toHaveCount(3, { timeout: 15_000 });
  await expect(first).toContainText(["[번역] Body text before the equation", "[번역] The equation above sums two terms.", "[번역] The second equation has no number"]);
  for (const text of ["Synthetic Parts Journal", "7:1", "x = a + b", "(1)", "f g h k"]) {
    await expect(translated(page, 0)).not.toContainText(text);
    expect(JSON.stringify(translationRuns().at(-1)!.message)).not.toContain(text);
  }
  // 표: 캡션과 본문만, 칸은 원문 그림 그대로
  await goToPage(page, 2);
  const second = translated(page, 1).locator(".translated-block");
  await expect(second).toHaveCount(2, { timeout: 15_000 });
  await expect(second).toContainText(["[번역] Table 1. [번역] Synthetic table of values.", "[번역] The table lists two values."]);
  await expect(translated(page, 1)).not.toContainText("alpha");
});

test("글로 읽기: 번역문만 큰 글자로, 문장 강조, 번역 글꼴 크기, 닫기", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "dpr-1", "번역 흐름은 DPR과 무관하다");
  const uploaded = await prepare(page);
  await openReader(page, uploaded);
  await page.getByRole("button", { name: "쪽 번역", exact: true }).click();
  await page.getByRole("button", { name: /^보기 방식/ }).click();
  await page.getByRole("menuitemradio", { name: /글로 읽기/ }).click();
  const panel = page.locator(".translation-reflow");
  const text = panel.locator(".translation-text");
  await expect(text).toContainText("[번역] Navigation fixture text for the outline and the find bar. [번역] Section one introduces the cache model.", { timeout: 15_000 });
  await expect(page.locator(".translated-page")).toHaveCount(0); // 레이아웃 유지 쪽은 없다
  await expect(text).toHaveCSS("font-size", "16px"); // 번역 글꼴을 따로 정하지 않으면 글꼴 크기 + 2

  await text.locator(".translated-sentence", { hasText: "[번역] Section one" }).hover();
  await expect(page.locator('.page[data-page-number="1"] .source-overlay .quad-mark')).toHaveCount(1);
  // 원문 문장에 마우스를 올리면 번역문의 그 문장을 강조한다 (2026-10-04 사용자 요청: 반대 방향)
  const sentence = await textRect(page, 1, "Section one introduces the cache model.");
  await page.mouse.move((sentence.left + sentence.right) / 2, (sentence.top + sentence.bottom) / 2);
  await expect(text.locator(".translated-sentence.is-linked")).toHaveText("[번역] Section one introduces the cache model.");
  await page.mouse.move(5, 5);
  await expect(text.locator(".translated-sentence.is-linked")).toHaveCount(0);

  await panel.getByRole("button", { name: "번역 글꼴 크기", exact: true }).click();
  await panel.getByRole("button", { name: "번역 글꼴 크게" }).click();
  await expect(text).toHaveCSS("font-size", "17px");
  await expect.poll(async () => (await (await page.request.get("/api/v1/settings")).json()).translation_font_size).toBe(17);

  // 보기 방식을 기억한다
  await page.reload();
  await expect(page.locator(".translation-reflow .translation-text")).toBeVisible();
  await page.locator(".translation-reflow").getByRole("button", { name: "번역 닫기" }).click();
  await expect(page.locator(".translation-reflow")).toHaveCount(0);
  await expect(page.locator(".translation-bar")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "쪽 번역", exact: true })).toHaveAttribute("aria-pressed", "false");
});

test("번역 모두 지우기: 확인하면 이 논문의 번역을 모두 지우고 보는 쪽은 다시 번역한다, 취소하면 그대로다", async ({ page }, testInfo) => {
  // 2026-10-04 사용자 요청(작은 개선). REST만 있던 것을 번역 도구에 둔다
  test.skip(testInfo.project.name !== "dpr-1", "번역 흐름은 DPR과 무관하다");
  const uploaded = await prepare(page);
  await openReader(page, uploaded);
  await page.getByRole("button", { name: "쪽 번역", exact: true }).click();
  await expect(translated(page, 0).locator(".translated-block").first()).toHaveText("[번역] Paperloom Navigation Sample", { timeout: 15_000 });
  await goToPage(page, 2);
  await expect(translated(page, 1).locator(".translated-block").first()).toHaveText("[번역] 2 Method", { timeout: 15_000 });
  const saved = async () => (await (await page.request.get(`/api/v1/versions/${uploaded.versionId}/translations/ko`)).json()).pages;
  expect(await saved()).toEqual([0, 1]);
  const before = translationRuns().length;
  const clear = page.locator(".translation-bar").getByRole("button", { name: "번역 모두 지우기" });

  // 취소하면 그대로다
  page.once("dialog", (dialog) => void dialog.dismiss());
  await clear.click();
  await page.waitForTimeout(300);
  expect(await saved()).toEqual([0, 1]);

  // 확인하면 모두 지우고, 보고 있는 쪽(2쪽)은 바로 다시 번역한다
  page.once("dialog", (dialog) => {
    expect(dialog.message()).toContain("번역을 모두 지울까요");
    void dialog.accept();
  });
  await clear.click();
  await expect.poll(() => translationRuns().length).toBe(before + 1);
  await expect.poll(saved).toEqual([1]);
  await expect(translated(page, 1).locator(".translated-block").first()).toHaveText("[번역] 2 Method");
});

test("모든 쪽 번역: 사용자가 시작하면 남은 쪽을 한 쪽씩, 본문 없는 쪽(참고문헌뿐)은 빼고 번역한다", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "dpr-1", "번역 흐름은 DPR과 무관하다");
  const uploaded = await prepare(page);
  await openReader(page, uploaded);
  const before = translationRuns().length;
  // 보는 쪽만 문단 묶음으로 나눠 동시에 번역하게 하고(split), 모든 쪽 번역의 다른 쪽은 통째로 (2026-10-03 사용자 결정)
  const requests: { page: number; split: boolean }[] = [];
  page.on("request", (request) => {
    if (request.method() === "POST" && request.url().endsWith("/translate-page")) {
      const body = request.postDataJSON() as { page_index: number; split: boolean };
      requests.push({ page: body.page_index, split: body.split });
    }
  });
  await page.getByRole("button", { name: "쪽 번역", exact: true }).click();
  await expect(translated(page, 0).locator(".translated-block").first()).toBeVisible({ timeout: 15_000 });
  const toolbar = page.locator(".translation-bar .translation-toolbar");
  await expect(toolbar).toContainText("모든 쪽");
  await toolbar.getByRole("button", { name: "시작" }).click();
  await expect(toolbar).toContainText("모든 쪽 번역함", { timeout: 30_000 });
  const pages = await (await page.request.get(`/api/v1/versions/${uploaded.versionId}/translations/ko`)).json();
  expect(pages.pages).toEqual([0, 1, 2]); // 4쪽은 참고문헌뿐(본문 없음)
  expect(translationRuns().length).toBe(before + 3); // 합성 쪽은 짧아 보는 쪽도 한 묶음이다
  expect(requests).toEqual([
    { page: 0, split: true },
    { page: 1, split: false },
    { page: 2, split: false },
  ]);

  await goToPage(page, 4);
  const status = page.locator(".translation-bar .translation-bar-status");
  await expect(status).toContainText("이 쪽에는 번역할 본문이 없습니다");
  await expect(status.getByRole("button")).toHaveCount(0);
  await page.waitForTimeout(300);
  expect(translationRuns().length).toBe(before + 3);
});

test("참고문헌 쪽 전체가 아니라 참고문헌 부분만 빼고, 같은 쪽의 본문은 저절로 번역한다", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "dpr-1", "번역 흐름은 DPR과 무관하다");
  const uploaded = await prepare(page, "text-references.pdf");
  await openReader(page, uploaded);
  await page.getByRole("button", { name: "쪽 번역", exact: true }).click();
  await expect(translated(page, 0).locator(".translated-block").first()).toBeVisible({ timeout: 15_000 });
  await goToPage(page, 2); // 본문 뒤에 References 머리와 항목이 있는 쪽
  const blocks = translated(page, 1).locator(".translated-block");
  await expect(blocks).toHaveCount(2, { timeout: 15_000 });
  await expect(blocks).toContainText(["[번역] 2 Method", "[번역] The method page holds the sigmaword term"]);
  await expect(translated(page, 1)).not.toContainText("A. Author");
  expect(JSON.stringify(translationRuns().at(-1)!.message)).not.toContain("A. Author");
  // 원문 글은 흰 바탕 층(.translated-mask)이 가리고 번역문 상자에는 바탕이 없다(겹친 문단이 앞 문단 번역을 가리지 않는다)
  await expect(translated(page, 1).locator(".translated-mask")).toHaveCount(2);
  await expect(blocks.first()).toHaveCSS("background-color", "rgba(0, 0, 0, 0)");
});

test("별도 탭: 모든 쪽을 이어 스크롤하며(마우스 휠) 두 탭의 쪽 이동을 맞추고, 그 탭의 문장 강조를 원문 탭에 그린다", async ({ page, context }, testInfo) => {
  test.skip(testInfo.project.name !== "dpr-1", "번역 흐름은 DPR과 무관하다");
  const uploaded = await prepare(page);
  await openReader(page, uploaded);
  await page.getByRole("button", { name: "쪽 번역", exact: true }).click();
  await page.getByRole("button", { name: /^보기 방식/ }).click();
  const [tab] = await Promise.all([context.waitForEvent("page"), page.getByRole("menuitemradio", { name: /별도 브라우저 탭/ }).click()]);
  await expect(tab).toHaveURL(new RegExp(`/reader/${uploaded.paperId}/translation\\?version=${uploaded.versionId}&page=1`));
  await expect(page.locator(".translation-bar")).toContainText("번역을 별도 탭에서 보는 중");
  await expect(page.locator(".translated-page")).toHaveCount(0);
  await expect(translated(tab, 0).locator(".translated-block").first()).toHaveText("[번역] Paperloom Navigation Sample", { timeout: 15_000 });
  await expect(tab.locator(".translation-tab-link")).toContainText("원문 탭과 연결됨");
  await expect(tab.locator("[data-tab-page]")).toHaveCount(4); // 모든 쪽이 이어진다

  // 번역 탭에서 마우스 휠로 2쪽까지 → 원문 탭도 2쪽
  const body = tab.locator(".translation-tab-body");
  const bodyBox = (await body.boundingBox())!;
  await tab.mouse.move(bodyBox.x + bodyBox.width / 2, bodyBox.y + bodyBox.height / 2);
  const pageHeight = (await translated(tab, 0).boundingBox())!.height;
  await tab.mouse.wheel(0, pageHeight * 0.9);
  await expect(tab).toHaveURL(/page=2$/);
  await expect(page.locator(".page-box")).toHaveAttribute("data-page", "2");
  await expect(translated(tab, 1).locator(".translated-block").first()).toHaveText("[번역] 2 Method", { timeout: 15_000 });

  // 원문 탭에서 3쪽 → 번역 탭이 3쪽 위로 스크롤한다
  await goToPage(page, 3);
  await expect(tab).toHaveURL(/page=3$/);
  await expect.poll(async () => (await tab.locator('[data-tab-page="2"]').boundingBox())!.y - bodyBox.y).toBeLessThan(40);
  await expect(translated(tab, 2).locator(".translated-block").last()).toHaveText("[번역] The results show a smaller cache delay.", { timeout: 15_000 });
  await tab.waitForTimeout(300);
  await expect(page.locator(".page-box")).toHaveAttribute("data-page", "3"); // 되돌려 보내지 않는다

  // 번역 탭에서 문장에 마우스를 올리면 원문 탭의 그 문장을 강조한다
  await translated(tab, 2).locator(".translated-sentence", { hasText: "[번역] The results show" }).hover();
  await expect(page.locator('.page[data-page-number="3"] .source-overlay .quad-mark')).toHaveCount(1);
  await tab.mouse.move(5, 5);
  await expect(page.locator('.page[data-page-number="3"] .source-overlay .quad-mark')).toHaveCount(0);
  // 원문 탭의 원문 문장에 마우스를 올리면 번역 탭의 그 번역 문장을 강조한다 (2026-10-04 사용자 요청: 반대 방향).
  // 원문 탭은 그 쪽의 저장된 번역을 처음 마우스를 올릴 때 읽는다(번역하지 않는다)
  const results = await textRect(page, 3, "The results show a smaller cache delay.");
  const tabLinked = translated(tab, 2).locator(".translated-sentence.is-linked");
  await expect
    .poll(async () => {
      await page.mouse.move((results.left + results.right) / 2 + Math.random(), (results.top + results.bottom) / 2);
      return tabLinked.count();
    })
    .toBe(1);
  await expect(tabLinked).toHaveText("[번역] The results show a smaller cache delay.");
  await page.mouse.move(5, 5);
  await expect(tabLinked).toHaveCount(0);

  // 화살표도 쪽으로 스크롤한다
  await tab.getByRole("button", { name: "앞 쪽" }).click();
  await expect(tab).toHaveURL(/page=2$/);
  await expect(page.locator(".page-box")).toHaveAttribute("data-page", "2");
  await expect.poll(async () => (await tab.locator('[data-tab-page="1"]').boundingBox())!.y - bodyBox.y).toBeLessThan(40);

  // 이 탭에서 보기로 돌아온다
  await page.getByRole("button", { name: "이 탭에서 보기" }).click();
  await expect(translated(page, 2).locator(".translated-block").last()).toHaveText("[번역] The results show a smaller cache delay.", { timeout: 15_000 });
});

test("별도 탭: 쪽 안 자리까지 맞춘다 — 원문 탭을 쪽 중간까지 스크롤하면 번역 탭도 그 쪽의 같은 자리를 위에 두고, 번역 탭을 스크롤하면 원문 탭이 따라온다", async ({ page, context }, testInfo) => {
  // 2026-10-04 사용자 확인: 쪽 번호만 맞춰 두 창을 나란히 두면 같은 쪽의 위치가 어긋났다
  test.skip(testInfo.project.name !== "dpr-1", "번역 흐름은 DPR과 무관하다");
  const uploaded = await prepare(page);
  await openReader(page, uploaded);
  await page.getByRole("button", { name: "쪽 번역", exact: true }).click();
  await page.getByRole("button", { name: /^보기 방식/ }).click();
  const [tab] = await Promise.all([context.waitForEvent("page"), page.getByRole("menuitemradio", { name: /별도 브라우저 탭/ }).click()]);
  await expect(translated(tab, 0).locator(".translated-block").first()).toBeVisible({ timeout: 15_000 });
  await expect(tab.locator(".translation-tab-link")).toContainText("원문 탭과 연결됨");

  /** 스크롤 영역 위끝이 그 쪽(테두리 안)의 어디인지: 쪽 높이에 대한 비율 */
  const at = (target: Page, container: string, pageSelector: string) =>
    target.evaluate(
      ([containerSelector, selector]) => {
        const top = document.querySelector(containerSelector)!.getBoundingClientRect().top;
        const element = document.querySelector<HTMLElement>(selector)!;
        return (top - element.getBoundingClientRect().top - element.clientTop) / element.clientHeight;
      },
      [container, pageSelector] as const,
    );
  const readerAt = (number: number) => at(page, ".reader-scroll", `.pdfViewer .page[data-page-number="${number}"]`);
  const tabAt = (number: number) => at(tab, ".translation-tab-body", `.translated-page[data-page-index="${number - 1}"]`);

  // 원문 탭: 2쪽의 40% 자리를 위끝에 → 번역 탭도 2쪽 40% 자리
  await page.locator(".reader-scroll").evaluate((element) => {
    const target = element.querySelector<HTMLElement>('.pdfViewer .page[data-page-number="2"]')!;
    element.scrollTop += target.getBoundingClientRect().top + target.clientTop + 0.4 * target.clientHeight - element.getBoundingClientRect().top;
  });
  await expect.poll(() => tabAt(2)).toBeCloseTo(0.4, 2);
  expect(await readerAt(2)).toBeCloseTo(0.4, 2);

  // 번역 탭: 휠로 쪽 높이의 반만큼 → 원문 탭도 그 자리(2쪽 90%). 원문 탭은 받은 자리로 옮긴 스크롤을 되돌려 보내지 않는다
  // (이어 스크롤하는 동안 늦게 닿은 앞 자리로 번역 탭이 끌려가 흔들리지 않게)
  await page.evaluate(() => {
    const posted: unknown[] = [];
    Object.assign(window, { posted });
    const post = BroadcastChannel.prototype.postMessage;
    BroadcastChannel.prototype.postMessage = function (message: unknown) {
      posted.push(message);
      return post.call(this, message);
    };
  });
  const body = (await tab.locator(".translation-tab-body").boundingBox())!;
  await tab.mouse.move(body.x + body.width / 2, body.y + body.height / 2);
  await tab.mouse.wheel(0, (await translated(tab, 1).boundingBox())!.height / 2);
  await expect.poll(() => tabAt(2)).toBeCloseTo(0.9, 2);
  await expect.poll(() => readerAt(2)).toBeCloseTo(0.9, 2);
  await page.waitForTimeout(300);
  expect(await tabAt(2)).toBeCloseTo(0.9, 2);
  const posted = await page.evaluate(() => (window as unknown as { posted: { type: string }[] }).posted);
  expect(posted.filter((message) => message.type === "scroll")).toEqual([]);
});

test("별도 탭: Ctrl+휠로 번역 쪽만 확대·축소하고(커서 아래 자리를 지킨다) Ctrl+0으로 되돌린다", async ({ page, context }, testInfo) => {
  test.skip(testInfo.project.name !== "dpr-1", "번역 흐름은 DPR과 무관하다");
  const uploaded = await prepare(page);
  await openReader(page, uploaded);
  await page.getByRole("button", { name: "쪽 번역", exact: true }).click();
  await page.getByRole("button", { name: /^보기 방식/ }).click();
  const [tab] = await Promise.all([context.waitForEvent("page"), page.getByRole("menuitemradio", { name: /별도 브라우저 탭/ }).click()]);
  await expect(translated(tab, 0).locator(".translated-block").first()).toBeVisible({ timeout: 15_000 });
  const before = (await translated(tab, 0).boundingBox())!;
  const head = (await tab.locator(".translation-tab-head").boundingBox())!;

  // 커서를 1쪽 위에 두고 Ctrl+휠 한 칸 위로: 번역 쪽만 1.2배(브라우저 확대가 아니라 머리는 그대로), 커서 아래 자리는 세로로 제자리
  const [x, y] = [before.x + before.width * 0.3, before.y + 200];
  await tab.mouse.move(x, y);
  await tab.keyboard.down("Control");
  await tab.mouse.wheel(0, -100);
  await tab.keyboard.up("Control");
  await expect.poll(async () => (await translated(tab, 0).boundingBox())!.width).toBeCloseTo(before.width * 1.2, 0);
  const after = (await translated(tab, 0).boundingBox())!;
  expect(Math.abs(after.y + ((y - before.y) / before.height) * after.height - y)).toBeLessThan(3);
  expect((await tab.locator(".translation-tab-head").boundingBox())!.height).toBeCloseTo(head.height, 0);
  expect(await tab.evaluate(() => window.devicePixelRatio)).toBe(1); // 브라우저 확대가 아니다

  // Ctrl+- 한 단계(110%), Ctrl+0은 처음 크기
  await tab.keyboard.press("Control+-");
  await expect.poll(async () => (await translated(tab, 0).boundingBox())!.width).toBeCloseTo(before.width * 1.1, 0);
  await tab.keyboard.press("Control+0");
  await expect.poll(async () => (await translated(tab, 0).boundingBox())!.width).toBeCloseTo(before.width, 0);
});
