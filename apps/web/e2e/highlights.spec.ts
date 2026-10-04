/**
 * U5 하이라이트 3색 (UI_PLAN §5 U5, IMPL §10.9): 선택 메뉴의 견본으로 색을 골라 칠하고, H는 마지막 색이다.
 * 하이라이트 패널에서 색을 바꾸고, 색으로 거르고, 찾고, 지운다. 겹친 하이라이트는 둘 다 그리고 곱하기로 섞는다.
 * 그사이 바뀐 주석의 색을 바꾸면(revision 충돌) 최신을 불러와 알린다. 메모 주석(C)은 하이라이트가 아니다.
 *
 * text-references.pdf 1쪽: "Prior work [1] measured cache delays and [2] split" / "the cache so that the rhoword term stays bounded."
 */
import { readFileSync } from "node:fs";

import { expect, type Page, test } from "@playwright/test";

import { clearAnnotations, FIXTURE_DIR, menuItem, openFixture, openPanel, saveNote, SELECTION_STATUS, showPage, uploadPdf } from "./fixture";

const FILE = "text-references.pdf";
const PDF = readFileSync(new URL(FILE, FIXTURE_DIR));
const FIRST = "Prior work [1] measured cache delays and [2] split";
const SECOND = "the cache so that the rhoword term stays bounded.";

/** 1쪽 줄 조각의 글자 [start, end)를 고른다(PDF.js가 다시 그리는 중이면 다시 한다). */
async function selectPart(page: Page, line: string, start: number, end: number) {
  await showPage(page, 0);
  for (let attempt = 1; ; attempt++) {
    await page.evaluate(
      ({ line, start, end }) => {
        const span = [...document.querySelectorAll('.page[data-page-number="1"] .textLayer span')].find((item) => item.textContent === line);
        if (!span) throw new Error(`span 없음: ${line}`);
        const range = document.createRange();
        range.setStart(span.firstChild!, start);
        range.setEnd(span.firstChild!, end);
        document.getSelection()!.removeAllRanges();
        document.getSelection()!.addRange(range);
      },
      { line, start, end },
    );
    try {
      await expect(page.locator(SELECTION_STATUS)).toContainText(line.slice(start, end).trim(), { timeout: 3000 });
      await expect(page.locator(".selection-menu")).toBeVisible({ timeout: 3000 });
      return;
    } catch (error) {
      if (attempt === 3) throw error;
    }
  }
}

async function openClean(page: Page) {
  const { versionId } = await uploadPdf(page, PDF, FILE);
  await clearAnnotations(page, versionId); // E2E 데이터 폴더는 실행 사이에 남는다
  await openFixture(page, PDF, FILE);
  return versionId;
}

const marks = (page: Page) => page.locator('.page[data-page-number="1"] > .annotation-overlay > .quad-mark');
const items = (page: Page) => page.locator(".highlight-list .note-item");

test("하이라이트: 견본 색으로 칠하고 H는 마지막 색이며, 패널에서 색을 바꾸고 거르고 찾고 지운다", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "dpr-1", "색·패널 흐름은 DPR과 무관하다(표시 좌표는 기존 시험이 본다)");
  const versionId = await openClean(page);

  // 1) 견본(회색)으로 칠한다. 레일 배지가 하나다
  await selectPart(page, FIRST, 0, "Prior work".length);
  await menuItem(page, "하이라이트: 회색").click();
  await expect(page.getByText("하이라이트를 저장했습니다.")).toBeVisible();
  await expect(marks(page)).toHaveCount(1);
  await expect(marks(page).first()).toHaveAttribute("data-color", "c3");
  const rail = page.getByRole("navigation", { name: "사이드바 패널" }).getByRole("button", { name: "하이라이트", exact: true });
  await expect(rail.locator(".rail-badge")).toHaveText("1");

  // 2) H는 마지막에 고른 색(회색)이다. 다시 열어도 기억한다
  await page.reload();
  await selectPart(page, SECOND, 0, "the cache".length);
  await page.keyboard.press("KeyH");
  await expect(marks(page)).toHaveCount(2);
  await expect(page.locator('.annotation-overlay > .quad-mark[data-color="c3"]')).toHaveCount(2);

  // 3) 패널: 쪽 순서로 보이고, 첫 하이라이트를 연한 주황으로 바꾸면 본문 색도 바뀐다
  await openPanel(page, "하이라이트");
  await expect(items(page)).toHaveCount(2);
  await expect(items(page).first()).toContainText("Prior work");
  await items(page).first().getByRole("button", { name: "연한 주황으로" }).click();
  await expect(items(page).first()).toHaveAttribute("data-color", "c1");
  await expect(page.locator('.annotation-overlay > .quad-mark[data-color="c1"]')).toHaveCount(1);
  await expect(items(page).first().getByRole("button", { name: "연한 주황으로" })).toHaveAttribute("aria-pressed", "true");

  // 4) 색으로 거르기와 찾기
  const filter = page.getByRole("group", { name: "색으로 거르기" });
  await filter.getByRole("button", { name: "회색" }).click();
  await expect(items(page)).toHaveCount(1);
  await expect(items(page).first()).toContainText("Prior work");
  await filter.getByRole("button", { name: "회색" }).click();
  await page.getByRole("searchbox", { name: "하이라이트 검색" }).fill("CACHE");
  await expect(items(page)).toHaveCount(1);
  await expect(items(page).first()).toContainText("the cache");
  await page.getByRole("searchbox", { name: "하이라이트 검색" }).fill("");

  // 5) 새로고침해도 색이 남는다(서버에 저장)
  await page.reload();
  await expect(page.locator('.annotation-overlay > .quad-mark[data-color="c1"]')).toHaveCount(1);
  await expect(page.locator('.annotation-overlay > .quad-mark[data-color="c3"]')).toHaveCount(1);

  // 6) 메모 주석(C)은 하이라이트가 아니다: 주석 패널에만 있다
  await selectPart(page, FIRST, "Prior work [1] ".length, "Prior work [1] measured".length);
  await menuItem(page, "주석").click();
  await saveNote(page, "측정 방법 메모");
  await openPanel(page, "하이라이트");
  await expect(items(page)).toHaveCount(2);
  await expect(rail.locator(".rail-badge")).toHaveText("2");
  await openPanel(page, "주석");
  await expect(page.locator(".note-list:not(.highlight-list) .note-item")).toHaveCount(3);

  // 7) 패널에서 지운다
  await openPanel(page, "하이라이트");
  page.once("dialog", (dialog) => void dialog.accept());
  await items(page).first().getByRole("button", { name: "삭제" }).click();
  await expect(items(page)).toHaveCount(1);
  await expect(page.locator('.annotation-overlay > .quad-mark[data-color]')).toHaveCount(1);
  await clearAnnotations(page, versionId);
});

test("겹친 하이라이트는 둘 다 곱하기로 그리고, 그사이 바뀐 주석의 색을 바꾸면 최신을 불러와 알린다", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "dpr-1", "색·패널 흐름은 DPR과 무관하다");
  const versionId = await openClean(page);

  // 겹친 두 하이라이트: "Prior work [1] measured"(연한 주황)와 "measured cache delays"(주황)
  await selectPart(page, FIRST, 0, "Prior work [1] measured".length);
  await menuItem(page, "하이라이트: 연한 주황").click();
  await expect(marks(page)).toHaveCount(1);
  const from = "Prior work [1] ".length;
  await selectPart(page, FIRST, from, from + "measured cache delays".length);
  await menuItem(page, "하이라이트: 주황").click();
  await expect(marks(page)).toHaveCount(2);
  const [first, second] = await Promise.all([
    page.locator('.annotation-overlay > .quad-mark[data-color="c1"]').boundingBox(),
    page.locator('.annotation-overlay > .quad-mark[data-color="c2"]').boundingBox(),
  ]);
  expect(second!.x).toBeLessThan(first!.x + first!.width); // "measured"에서 겹친다
  const blend = await page.locator('.page[data-page-number="1"] > .annotation-overlay').evaluate((layer) => [
    getComputedStyle(layer).mixBlendMode,
    getComputedStyle(layer.querySelector(".quad-mark[data-color]")!).mixBlendMode,
  ]);
  expect(blend).toEqual(["multiply", "multiply"]);

  // 그사이 다른 곳에서 바뀐 주석: 색 바꾸기가 거부되고, 최신 색을 불러와 알린다
  await openPanel(page, "하이라이트");
  const listed = (await (await page.request.get(`/api/v1/versions/${versionId}/annotations`)).json()).annotations;
  const target = listed.find((annotation: { color: string }) => annotation.color === "c1");
  const behind = await page.request.patch(`/api/v1/annotations/${target.annotation_id}`, { data: { revision: target.revision, color: "c3" } });
  expect(behind.status()).toBe(200);
  const item = page.locator(`.highlight-list .note-item[data-annotation-id="${target.annotation_id}"]`);
  await item.getByRole("button", { name: "주황으로", exact: true }).click();
  await expect(item.getByRole("alert")).toContainText("그사이 다른 곳에서");
  await expect(item).toHaveAttribute("data-color", "c3");
  await expect(item).toHaveAttribute("data-revision", String(target.revision + 1));
  await clearAnnotations(page, versionId);
});
