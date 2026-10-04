/**
 * W05 (G3): Library의 본문 추출 상태, 논문 제목 검색, 쪽만 연 주소, Reader의 쪽 추출 상태 표시.
 * 합성 fixture(tests/fixtures/pdf-layout/text-*.pdf)를 쓴다. 검색은 제목만 찾는다(2026-10-01 사용자 결정).
 * U6부터 제목 검색은 서재 머리의 입력칸이다(Enter). 찾은 논문만 서재 표에 남고 찾은 낱말을 표시한다.
 */
import { readFileSync } from "node:fs";

import { expect, type Page, test } from "@playwright/test";

import { FIXTURE_DIR, type Uploaded, uploadPdf } from "./fixture";

const pdf = (name: string) => readFileSync(new URL(name, FIXTURE_DIR));

async function uploadAll(page: Page): Promise<Record<string, Uploaded>> {
  const uploaded: Record<string, Uploaded> = {};
  for (const name of ["text-digital.pdf", "text-mixed.pdf", "text-image-only.pdf"]) {
    uploaded[name] = await uploadPdf(page, pdf(name), name);
  }
  return uploaded;
}

async function runSearch(page: Page, query: string) {
  await page.getByLabel("제목 검색어").fill(query);
  await page.getByLabel("제목 검색어").press("Enter");
}

/** 서재 표의 그 논문 제목 단추 */
function titleButton(page: Page, paperId: string) {
  return page.locator(`tr[data-paper-id="${paperId}"] .paper-open`);
}

test("Library가 문서별 본문 추출 상태를 보이고, 끝날 때까지 다시 받는다", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "dpr-1", "목록 표시는 DPR과 무관하다");
  const uploaded = await uploadAll(page);
  const digitalId = uploaded["text-digital.pdf"].paperId;
  // fixture 추출은 1초도 걸리지 않으므로, 첫 목록에서 추출 중이었던 것처럼 바꿔 다시 받는지 확인한다.
  let firstList = true;
  await page.route("**/api/v1/papers", async (route) => {
    if (route.request().method() !== "GET" || !firstList) return route.fallback();
    firstList = false;
    const response = await route.fetch();
    const body = await response.json();
    for (const paper of body.papers) {
      if (paper.paper_id === digitalId) paper.current_version = { ...paper.current_version, status: "PARSING" };
    }
    await route.fulfill({ response, json: body });
  });
  await page.goto("/");

  const status = (name: string) => page.locator(`tr[data-paper-id="${uploaded[name].paperId}"] td[data-status]`);
  await expect(status("text-digital.pdf")).toHaveText("본문 추출 중");
  await expect(status("text-digital.pdf")).toHaveAttribute("data-status", "INDEXED", { timeout: 30_000 });
  await expect(status("text-digital.pdf")).toHaveText("검색 가능");
  await expect(status("text-mixed.pdf")).toHaveAttribute("data-status", "PARTIAL", { timeout: 30_000 });
  await expect(status("text-mixed.pdf")).toContainText("일부 쪽만 검색 가능");
  await expect(status("text-image-only.pdf")).toHaveAttribute("data-status", "FAILED", { timeout: 30_000 });
  await expect(status("text-image-only.pdf")).toContainText("검색 불가 · 글자 층 없음(스캔·이미지)");
  await expect(status("text-image-only.pdf").getByRole("button", { name: "다시 추출" })).toBeVisible();
  await expect(status("text-digital.pdf").getByRole("button")).toHaveCount(0);

  // 다시 추출: 대기 → 추출 중 → 같은 결과
  await status("text-image-only.pdf").getByRole("button", { name: "다시 추출" }).click();
  await expect(status("text-image-only.pdf")).toHaveAttribute("data-status", "FAILED", { timeout: 30_000 });
});

test("제목 검색: 앞부분만 써도 찾고, 본문 낱말은 찾지 않고, 잘못된 검색어는 이유를 알린다", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "dpr-1", "목록 표시는 DPR과 무관하다");
  const uploaded = await uploadAll(page);
  await page.goto("/");

  await runSearch(page, "synth mix");
  const mixed = titleButton(page, uploaded["text-mixed.pdf"].paperId);
  await expect(mixed).toBeVisible();
  await expect(mixed.locator("mark")).toHaveText(["mixed", "synthetic"]);
  await expect(titleButton(page, uploaded["text-digital.pdf"].paperId)).toHaveCount(0);
  await expect(page.getByRole("status").filter({ hasText: /제목에서 \d+편을 찾았습니다/ })).toBeVisible();

  await runSearch(page, "alphaword"); // text-digital.pdf 본문에만 있는 낱말
  await expect(page.getByRole("status").filter({ hasText: "제목에서 찾은 논문이 없습니다" })).toBeVisible();
  await expect(page.locator(".shelf-table tbody tr")).toHaveCount(0);
  await runSearch(page, "...");
  await expect(page.getByRole("status").filter({ hasText: "검색어에 글자나 숫자가 있어야 합니다." })).toBeVisible();

  // 검색을 지우면 서재 표가 모두 돌아온다
  await runSearch(page, "synth mix");
  await page.getByRole("button", { name: "검색 지우기" }).click();
  await expect(page.getByLabel("제목 검색어")).toHaveValue("");
  await expect(titleButton(page, uploaded["text-digital.pdf"].paperId)).toBeVisible();
  await expect(page.locator(".paper-open mark")).toHaveCount(0);
});

test("쪽만 연 주소는 그 쪽으로 가고, 이미지뿐인 쪽은 본문이 없다고 알린다", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "dpr-1", "상태 표시는 DPR과 무관하다");
  const { paperId, versionId } = (await uploadAll(page))["text-mixed.pdf"];
  await page.goto("/");
  await expect(page.locator(`tr[data-paper-id="${paperId}"] td[data-status]`)).toHaveAttribute("data-status", "PARTIAL", {
    timeout: 30_000,
  });

  await page.goto(`/reader/${paperId}?version=${versionId}&page=2`);
  await expect(page.getByLabel("쪽 번호")).toHaveValue("2");
  await expect(page.locator(".page-box")).toHaveAttribute("data-pages", "4");
  await expect(page.locator(".page-text-status")).toHaveAttribute("data-text-status", "image_only");
  await expect(page.locator(".page-text-status")).toHaveText("본문 없음 · 이미지");
  await page.goto(`/reader/${paperId}?version=${versionId}&page=4`);
  await expect(page.getByLabel("쪽 번호")).toHaveValue("4");
  await expect(page.locator(".page-text-status")).toHaveAttribute("data-text-status", "partial");
});

test("제목에서 찾은 논문을 누르면 그 논문을 연다", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "dpr-1", "목록 표시는 DPR과 무관하다");
  const { paperId } = (await uploadAll(page))["text-digital.pdf"];
  await page.goto("/");

  await runSearch(page, "synthetic digital");
  await titleButton(page, paperId).click();
  await expect(page).toHaveURL(new RegExp(`/reader/${paperId}\\?version=`));
  await expect(page.locator(".page-text-status")).toHaveAttribute("data-text-status", "usable");
});
