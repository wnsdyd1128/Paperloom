/**
 * 참고문헌 번호 따라가기 (2026-10-02 사용자 요청, IMPL §10.5): 본문의 "[2]"를 Ctrl을 누른 채 누르면 참고문헌 쪽의
 * 그 항목으로 스크롤해 그 줄을 강조한다. 그냥 누르거나 번호가 아닌 글을 Ctrl로 누르면 아무 일도 없다.
 * 간 뒤에는 "N쪽으로 돌아가기" 단추나 Alt+←로 보던 자리로 돌아온다. Ctrl을 누르고 번호 위에 있으면 손가락 커서다.
 *
 * text-references.pdf (tests/fixtures/pdf-layout/generate_text_extraction.py): 1쪽 본문 "Prior work [1] … [2] split",
 * 2쪽 "cites [3] once more."와 References 머리 뒤 한 줄 항목 [1]·[2], 3쪽 항목 [3]·[4], 4쪽 부록. 참고문헌 쪽은 2–3쪽.
 */
import { readFileSync } from "node:fs";

import { expect, type Locator, type Page, test } from "@playwright/test";

import { chooseZoom, FIXTURE_DIR, openFixture, uploadPdf } from "./fixture";

const FILE = "text-references.pdf";
const PDF = readFileSync(new URL(FILE, FIXTURE_DIR));
// 그냥 누른 뒤 따라가지 않았는지 볼 때 기다리는 시간(따라가면 쪽 문단을 받아 바로 강조한다)
const SETTLE_MS = 500;

/** 쪽의 text layer 조각 */
function span(page: Page, pageNumber: number, text: string): Locator {
  return page.locator(`.page[data-page-number="${pageNumber}"] .textLayer span`, { hasText: text }).first();
}

/** 조각을 화면에 보이게 하고, 조각 안 needle 글자들의 화면 가운데 */
async function center(target: Locator, needle: string) {
  await target.scrollIntoViewIfNeeded();
  return target.evaluate((element, needle) => {
    const node = element.firstChild as Text;
    const start = node.data.indexOf(needle);
    const range = document.createRange();
    range.setStart(node, start);
    range.setEnd(node, start + needle.length);
    const rect = range.getBoundingClientRect();
    return { x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 };
  }, needle);
}

async function click(page: Page, point: { x: number; y: number }, ctrl: boolean) {
  if (ctrl) await page.keyboard.down("Control");
  await page.mouse.click(point.x, point.y);
  if (ctrl) await page.keyboard.up("Control");
}

/** 따라간 항목의 강조(링크로 연 위치와 같은 표시) */
function focused(page: Page, pageNumber: number) {
  return page.locator(`.page[data-page-number="${pageNumber}"] > .annotation-overlay > .quad-mark.is-focused`);
}

/** 강조가 하나이고 entry 줄과 같은 높이에 있으며 스크롤 영역 안에 보인다 */
async function expectFollowed(page: Page, pageNumber: number, entry: string) {
  const mark = focused(page, pageNumber);
  await expect(mark).toHaveCount(1);
  const line = span(page, pageNumber, entry);
  await expect
    .poll(async () => {
      const [box, text, scroller] = await Promise.all([mark.boundingBox(), line.boundingBox(), page.locator(".reader-scroll").boundingBox()]);
      const aligned = Math.abs(box!.y + box!.height / 2 - (text!.y + text!.height / 2)) < text!.height / 2;
      const visible = box!.y >= scroller!.y && box!.y + box!.height <= scroller!.y + scroller!.height;
      return aligned && visible;
    }, { message: `${entry} 줄을 강조하고 그곳으로 스크롤` })
    .toBe(true);
}

/** 본문 추출이 참고문헌 쪽(2–3쪽)을 표시한 뒤에 연다 */
async function openReferences(page: Page) {
  const { versionId } = await uploadPdf(page, PDF, FILE);
  await expect
    .poll(
      async () => {
        const body = await (await page.request.get(`/api/v1/versions/${versionId}/pages`)).json();
        return [body.status, body.pages.filter((item: { flags: string[] }) => item.flags.includes("references")).map((item: { page_index: number }) => item.page_index)];
      },
      { timeout: 30_000 },
    )
    .toEqual(["INDEXED", [1, 2]]);
  await openFixture(page, PDF, FILE);
}

test("Ctrl+클릭한 참고문헌 번호는 참고문헌 쪽의 그 항목으로 가고, Esc로 강조를 지운다", async ({ page }) => {
  await openReferences(page);
  const body = span(page, 1, "Prior work [1]");

  // 1) 그냥 누르면 따라가지 않는다
  await click(page, await center(body, "[2]"), false);
  await page.waitForTimeout(SETTLE_MS);
  await expect(page.locator(".quad-mark.is-focused")).toHaveCount(0);

  // 2) Ctrl+클릭: 2쪽의 [2] 항목 줄(한 줄 항목이 이어 붙은 문단의 둘째 줄)
  await click(page, await center(body, "[2]"), true);
  await expectFollowed(page, 2, "[2] B. Author");

  // 3) 이미 받은 쪽의 다른 항목도 간다(빈 곳 누르기로 지우지 않는다)
  await click(page, await center(body, "[1]"), true);
  await expectFollowed(page, 2, "[1] A. Author");

  // 4) 2쪽 본문의 [3]은 3쪽 항목이다. 앞 강조는 사라진다
  await click(page, await center(span(page, 2, "cites [3]"), "[3]"), true);
  await expectFollowed(page, 3, "[3] C. Author");
  await expect(focused(page, 2)).toHaveCount(0);

  // 5) Esc로 지운다
  await page.keyboard.press("Escape");
  await expect(page.locator(".quad-mark.is-focused")).toHaveCount(0);

  // 6) 번호가 아닌 글을 Ctrl로 누르면 아무 일도 없다(안내도 없다)
  await click(page, await center(body, "measured"), true);
  await page.waitForTimeout(SETTLE_MS);
  await expect(page.locator(".quad-mark.is-focused")).toHaveCount(0);
  await expect(page.locator(".reader-toast")).toHaveCount(0);
});

/** 조각을 스크롤 영역 가운데에 둔다(쪽 끝이면 스크롤할 수 있는 만큼) */
async function centerOn(target: Locator) {
  await target.evaluate((element) => element.scrollIntoView({ block: "center", inline: "center" }));
}

/** 조각과 스크롤 영역 가운데의 세로 거리 */
async function offCenter(page: Page, target: Locator) {
  const [box, scroller] = await Promise.all([target.boundingBox(), page.locator(".reader-scroll").boundingBox()]);
  return Math.abs(box!.y + box!.height / 2 - (scroller!.y + scroller!.height / 2));
}

test("참고문헌으로 간 뒤 돌아가기 단추·Alt+←로 보던 자리로 차례로 돌아오고, 확대를 바꿔도 같은 곳이다", async ({ page }) => {
  await openReferences(page);
  const scroller = page.locator(".reader-scroll");
  const scrollTop = () => scroller.evaluate((element) => element.scrollTop);
  const back = page.locator(".reader-return");
  const backTo = (pageNumber: number) => back.getByRole("button", { name: `${pageNumber}쪽으로 돌아가기` });
  const body = span(page, 1, "Prior work [1]");
  const cites = span(page, 2, "cites [3]");
  await page.evaluate(() => {
    window.addEventListener("keydown", (event) => {
      if (event.key === "ArrowLeft") (window as unknown as { altLeft: boolean }).altLeft = event.defaultPrevented;
    });
  });

  // 1) 2쪽 본문(A)에서 [3]으로, 1쪽 본문(B)에서 [2]로 간다. 단추는 마지막에 보던 쪽이다
  await centerOn(cites);
  const atA = await scrollTop();
  await click(page, await center(cites, "[3]"), true);
  await expectFollowed(page, 3, "[3] C. Author");
  await expect(backTo(2)).toBeVisible();
  await centerOn(body);
  const atB = await scrollTop();
  await click(page, await center(body, "[2]"), true);
  await expectFollowed(page, 2, "[2] B. Author");
  await expect(backTo(1)).toBeVisible();

  // 2) Alt+←는 B로 돌아오고(브라우저 뒤로 가기가 아니다), 강조를 지운다. 단추는 이제 A다
  const url = page.url();
  await page.keyboard.press("Alt+ArrowLeft");
  await expect.poll(async () => Math.abs((await scrollTop()) - atB), { message: "B로 돌아옴" }).toBeLessThanOrEqual(1);
  expect(await page.evaluate(() => (window as unknown as { altLeft: boolean }).altLeft)).toBe(true);
  expect(page.url()).toBe(url);
  await expect(page.locator(".quad-mark.is-focused")).toHaveCount(0);
  await expect(backTo(2)).toBeVisible();

  // 3) 단추는 A로 돌아오고, 더 돌아갈 곳이 없으면 사라진다
  await backTo(2).click();
  await expect.poll(async () => Math.abs((await scrollTop()) - atA), { message: "A로 돌아옴" }).toBeLessThanOrEqual(1);
  await expect(back).toHaveCount(0);

  // 4) 간 뒤 확대를 바꿔도 보던 줄이 스크롤 영역 가운데로 돌아온다
  await centerOn(cites);
  await click(page, await center(cites, "[3]"), true);
  await expectFollowed(page, 3, "[3] C. Author");
  await chooseZoom(page, 1.5);
  await backTo(2).click();
  await expect.poll(() => offCenter(page, cites), { message: "확대 뒤에도 보던 줄로" }).toBeLessThanOrEqual(2);

  // 5) 닫기(×)는 움직이지 않고 단추만 없앤다
  await click(page, await center(cites, "[3]"), true);
  await expectFollowed(page, 3, "[3] C. Author");
  const here = await scrollTop();
  await back.getByRole("button", { name: "돌아가기 닫기" }).click();
  await expect(back).toHaveCount(0);
  expect(await scrollTop()).toBe(here);
});

test("Ctrl을 누르고 참고문헌 번호 위에 있으면 손가락 커서다", async ({ page }) => {
  await openReferences(page);
  const body = span(page, 1, "Prior work [1]");
  const number = await center(body, "[2]");
  const word = await center(body, "measured");
  const cursorAt = (point: { x: number; y: number }) =>
    page.evaluate(({ x, y }) => {
      const element = document.elementsFromPoint(x, y).find((item) => item.matches(".textLayer span"));
      return element ? getComputedStyle(element).cursor : null;
    }, point);

  // 번호 위에서 Ctrl을 누르면(움직이지 않아도) 손가락, 번호가 아닌 글은 글자 커서, 떼면 글자 커서
  await page.mouse.move(number.x, number.y);
  await expect.poll(() => cursorAt(number)).toBe("text");
  await page.keyboard.down("Control");
  await expect.poll(() => cursorAt(number)).toBe("pointer");
  await page.mouse.move(word.x, word.y);
  await expect.poll(() => cursorAt(word)).toBe("text");
  await page.mouse.move(number.x, number.y);
  await expect.poll(() => cursorAt(number)).toBe("pointer");
  await page.keyboard.up("Control");
  await expect.poll(() => cursorAt(number)).toBe("text");
});
