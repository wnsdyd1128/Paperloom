/**
 * U6 서재 (docs/UI_PLAN.md U6, 시안 Library): 태그 붙이기·거르기(하나라도/모두/태그 없음/빈 결과 안내), 끌어 놓기와
 * "PDF 등록" 올리기, 마지막 열람·차례, 주석·대화 개수. 합성 fixture(tests/fixtures/pdf-layout/text-*.pdf)를 쓴다.
 * E2E 데이터 폴더는 실행 사이에 남으므로 태그는 처음에 모두 지우고 시작한다.
 */
import { readFileSync } from "node:fs";

import { expect, type Page, test } from "@playwright/test";

import { FIXTURE_DIR, type Uploaded, uploadPdf } from "./fixture";

const FILES = ["text-digital.pdf", "text-mixed.pdf", "text-references.pdf"] as const;
type File = (typeof FILES)[number];

const pdf = (name: string) => readFileSync(new URL(name, FIXTURE_DIR));
const row = (page: Page, paperId: string) => page.locator(`tr[data-paper-id="${paperId}"]`);

async function uploadAll(page: Page): Promise<Record<File, Uploaded>> {
  const uploaded = {} as Record<File, Uploaded>;
  for (const name of FILES) uploaded[name] = await uploadPdf(page, pdf(name), name);
  return uploaded;
}

async function clearAllTags(page: Page) {
  const { papers } = await (await page.request.get("/api/v1/papers")).json();
  for (const paper of papers as { paper_id: string; tags: string[] }[]) {
    if (paper.tags.length > 0) expect((await page.request.put(`/api/v1/papers/${paper.paper_id}/tags`, { data: { tags: [] } })).status()).toBe(200);
  }
}

/** 줄의 "+"로 태그 창을 열고, 있는 태그는 켜고 새 태그는 적어 붙인다. */
async function addTags(page: Page, paperId: string, existing: string[], created: string[]) {
  await row(page, paperId).getByRole("button", { name: /태그 붙이기$/ }).click();
  const popover = page.getByRole("dialog", { name: "태그 붙이기" });
  for (const name of existing) await popover.getByRole("checkbox", { name, exact: true }).check();
  for (const name of created) {
    await popover.getByLabel("새 태그").fill(name);
    await popover.getByLabel("새 태그").press("Enter");
    await expect(row(page, paperId).locator(".tag-chip", { hasText: name })).toBeVisible();
  }
  await page.keyboard.press("Escape");
  await expect(popover).toHaveCount(0);
}

async function visibleRows(page: Page, uploaded: Record<File, Uploaded>): Promise<File[]> {
  const shown: File[] = [];
  for (const name of FILES) if ((await row(page, uploaded[name].paperId).count()) > 0) shown.push(name);
  return shown;
}

test("태그: 줄마다 붙이고(새로고침해도 남는다), 칩을 누르거나 메뉴에서 하나라도·모두·태그 없음으로 거르고, 빈 결과를 알린다", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "dpr-1", "서재 표는 DPR과 무관하다");
  const uploaded = await uploadAll(page);
  const id = (name: File) => uploaded[name].paperId;
  await clearAllTags(page);
  await page.goto("/");

  // 1) 붙이기: 새 태그는 적고, 서재에 있는 태그는 목록에서 켠다. 대소문자만 다르면 같은 태그다
  await addTags(page, id("text-digital.pdf"), [], ["Cache"]);
  await addTags(page, id("text-mixed.pdf"), [], ["WCET"]);
  await addTags(page, id("text-references.pdf"), ["Cache"], ["Scheduling", "cache"]);
  await expect(row(page, id("text-references.pdf")).locator(".tag-chip")).toHaveText(["Cache", "Scheduling"]);
  // 화면은 바로 바뀌고 저장은 차례로 간다. 마지막 저장이 끝나기 전에 새로고침하면 그 저장이 떠나지 못하므로 서버를 기다린다.
  const serverTags = async (name: File) => (await (await page.request.get(`/api/v1/papers/${id(name)}`)).json()).tags;
  await expect.poll(() => serverTags("text-references.pdf")).toEqual(["Cache", "Scheduling"]);
  await page.reload();
  await expect(row(page, id("text-digital.pdf")).locator(".tag-chip")).toHaveText(["Cache"]);
  await expect(row(page, id("text-references.pdf")).locator(".tag-chip")).toHaveText(["Cache", "Scheduling"]);
  const total = await page.locator(".shelf-table tbody tr").count();

  // 2) 칩을 누르면 그 태그로 거르고, 거르기 칩의 ×로 푼다
  await row(page, id("text-digital.pdf")).getByRole("button", { name: "Cache", exact: true }).click();
  expect(await visibleRows(page, uploaded)).toEqual(["text-digital.pdf", "text-references.pdf"]);
  await expect(page.getByTestId("shelf-count")).toHaveText(`2 / ${total}편`);
  await expect(row(page, id("text-digital.pdf")).getByRole("button", { name: "Cache", exact: true })).toHaveAttribute("aria-pressed", "true");
  await page.getByRole("button", { name: "Cache 거르기 빼기" }).click();
  await expect(page.getByTestId("shelf-count")).toHaveText(`${total}편`);

  // 3) 메뉴: 하나라도 → 모두 → 빈 결과 안내
  await page.getByRole("button", { name: "태그", exact: true }).click();
  const menu = page.getByRole("dialog", { name: "태그로 거르기" });
  await expect(menu.locator(".tag-check")).toHaveText(["Cache2", "Scheduling1", "WCET1", `태그 없음${total - 3}`]);
  await menu.getByRole("checkbox", { name: "Cache" }).check();
  await menu.getByRole("checkbox", { name: "WCET" }).check();
  expect(await visibleRows(page, uploaded)).toEqual(["text-digital.pdf", "text-mixed.pdf", "text-references.pdf"]);
  await expect(page.locator(".filter-chips")).toContainText("필터 · 하나라도");
  await menu.locator("label.seg-opt", { hasText: "모두" }).click(); // 숨은 라디오의 이름표
  await expect(menu.getByRole("radio", { name: "모두" })).toBeChecked();
  expect(await visibleRows(page, uploaded)).toEqual([]);
  await expect(page.locator(".shelf-empty")).toHaveText('고른 태그를 모두 가진 논문이 없습니다. "하나라도"로 바꾸거나 태그를 줄여 보세요.');
  await menu.getByRole("checkbox", { name: "WCET" }).uncheck();
  await menu.getByRole("checkbox", { name: "Scheduling" }).check();
  expect(await visibleRows(page, uploaded)).toEqual(["text-references.pdf"]);
  await menu.getByLabel("태그 찾기").fill("sch");
  await expect(menu.locator(".tag-check")).toHaveText(["Scheduling1", `태그 없음${total - 3}`]);

  // 4) 태그 없음: 태그를 고른 것은 풀고 태그 없는 논문만
  await menu.getByRole("checkbox", { name: "태그 없음" }).check();
  expect(await visibleRows(page, uploaded)).toEqual([]);
  await expect(page.locator(".shelf-table tbody tr")).toHaveCount(total - 3);
  await expect(page.getByTestId("shelf-count")).toHaveText(`${total - 3} / ${total}편`);
  await menu.getByRole("button", { name: "지우기", exact: true }).click();
  await menu.getByRole("button", { name: "닫기" }).click();
  await expect(menu).toHaveCount(0);
  await expect(page.getByTestId("shelf-count")).toHaveText(`${total}편`);

  // 5) 떼기: 아무 논문에도 없는 태그는 서재에서 사라진다
  await row(page, id("text-references.pdf")).getByRole("button", { name: /태그 붙이기$/ }).click();
  await page.getByRole("dialog", { name: "태그 붙이기" }).getByRole("checkbox", { name: "Scheduling", exact: true }).uncheck();
  await page.keyboard.press("Escape");
  await expect(row(page, id("text-references.pdf")).locator(".tag-chip")).toHaveText(["Cache"]);
  await page.getByRole("button", { name: "태그", exact: true }).click();
  await expect(menu.locator(".tag-check-name")).toHaveText(["Cache", "WCET", "태그 없음"]);
  await clearAllTags(page);
});

test("태그 관리: 태그 메뉴에서 이름을 바꾸면 모든 논문에서 바뀌고(고른 거르기도 따라간다), 지우면 모든 논문에서 뗀다", async ({ page }, testInfo) => {
  // 2026-10-04 사용자 요청(작은 개선)
  test.skip(testInfo.project.name !== "dpr-1", "서재 표는 DPR과 무관하다");
  const uploaded = await uploadAll(page);
  const id = (name: File) => uploaded[name].paperId;
  await clearAllTags(page);
  for (const [name, tags] of [["text-digital.pdf", ["ml", "Cache"]], ["text-mixed.pdf", ["ml"]]] as const) {
    expect((await page.request.put(`/api/v1/papers/${id(name)}/tags`, { data: { tags } })).status()).toBe(200);
  }
  await page.goto("/");
  const total = (await (await page.request.get("/api/v1/papers")).json()).papers.length;
  await page.getByRole("button", { name: "태그", exact: true }).click();
  const menu = page.getByRole("dialog", { name: "태그로 거르기" });
  await menu.getByRole("checkbox", { name: "ml" }).check();
  expect(await visibleRows(page, uploaded)).toEqual(["text-digital.pdf", "text-mixed.pdf"]);

  // 1) 이름 바꾸기: 모든 논문에서 바뀌고, 고른 거르기도 새 이름을 따른다
  await menu.getByRole("button", { name: "ml 태그 이름 바꾸기" }).click();
  const input = menu.getByRole("textbox", { name: "ml 새 이름" });
  await expect(input).toHaveValue("ml");
  await input.fill("Machine Learning");
  await input.press("Enter");
  await expect(row(page, id("text-digital.pdf")).locator(".tag-chip")).toHaveText(["Cache", "Machine Learning"]);
  await expect(row(page, id("text-mixed.pdf")).locator(".tag-chip")).toHaveText(["Machine Learning"]);
  await expect(menu.getByRole("checkbox", { name: "Machine Learning" })).toBeChecked();
  expect(await visibleRows(page, uploaded)).toEqual(["text-digital.pdf", "text-mixed.pdf"]);

  // 2) Esc는 이름 바꾸기만 그만둔다(메뉴는 열려 있고 이름은 그대로다)
  await menu.getByRole("button", { name: "Cache 태그 이름 바꾸기" }).click();
  await menu.getByRole("textbox", { name: "Cache 새 이름" }).fill("Caches");
  await menu.getByRole("textbox", { name: "Cache 새 이름" }).press("Escape");
  await expect(menu.getByRole("checkbox", { name: "Cache" })).toBeVisible();
  await expect(row(page, id("text-digital.pdf")).locator(".tag-chip")).toHaveText(["Cache", "Machine Learning"]);

  // 3) 지우기: 확인하면 모든 논문에서 뗀다(논문은 그대로, 그 태그로 거르던 것도 푼다)
  page.once("dialog", (dialog) => {
    expect(dialog.message()).toContain("모든 논문에서 지울까요");
    void dialog.accept();
  });
  await menu.getByRole("button", { name: "Machine Learning 태그 지우기" }).click();
  await expect(row(page, id("text-digital.pdf")).locator(".tag-chip")).toHaveText(["Cache"]);
  await expect(row(page, id("text-mixed.pdf")).locator(".tag-chip")).toHaveCount(0);
  await expect(page.getByTestId("shelf-count")).toHaveText(`${total}편`);
  await expect(menu.locator(".tag-check-name")).toHaveText(["Cache", "태그 없음"]);
  await clearAllTags(page);
});

test("PDF를 화면에 끌어다 놓거나 PDF 등록으로 올린다(같은 파일은 이미 등록됐다고 알린다), PDF가 아니면 올리지 않는다", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "dpr-1", "올리기는 DPR과 무관하다");
  const { paperId } = (await uploadAll(page))["text-digital.pdf"];
  const title: string = (await (await page.request.get(`/api/v1/papers/${paperId}`)).json()).title;
  await page.goto("/");
  await expect(page.locator(".shelf-table")).toBeVisible();

  // 1) 끌어 놓기: 끄는 동안 받침이 보이고, 놓으면 올린다 (이미 올린 바이트라 서버가 중복이라고 답한다).
  //    놓은 뒤에도 가운데 받침이 결과(여기서는 등록 실패)를 보여 준 뒤 사라진다
  const overlayDrop = page.locator(".drop-overlay .file-drop");
  const drop = async (name: string, type: string, base64: string) => {
    const transfer = await page.evaluateHandle(
      ({ name, type, base64 }) => {
        const bytes = Uint8Array.from(atob(base64), (char) => char.charCodeAt(0));
        const data = new DataTransfer();
        data.items.add(new File([bytes], name, { type }));
        return data;
      },
      { name, type, base64 },
    );
    await page.dispatchEvent(".library-main", "dragenter", { dataTransfer: transfer });
    await expect(page.locator(".drop-overlay")).toHaveAttribute("data-dragging", "true");
    await expect(overlayDrop).toHaveAttribute("data-phase", "idle");
    await page.dispatchEvent(".library-main", "dragover", { dataTransfer: transfer });
    await page.dispatchEvent(".library-main", "drop", { dataTransfer: transfer });
    await expect(overlayDrop).toHaveAttribute("data-phase", "failed");
    await expect(page.locator(".drop-overlay")).not.toHaveAttribute("data-dragging");
    await expect(page.locator(".drop-overlay")).toHaveCount(0, { timeout: 10_000 });
  };
  await drop("text-digital.pdf", "application/pdf", pdf("text-digital.pdf").toString("base64"));
  await expect(page.getByRole("status").filter({ hasText: `이미 등록된 논문입니다: ${title}` })).toBeVisible();
  await drop("memo.txt", "text/plain", Buffer.from("not a pdf").toString("base64"));
  await expect(page.getByRole("status").filter({ hasText: "PDF 파일만 올릴 수 있습니다." })).toBeVisible();

  // 2) PDF 등록 단추: 파일 고르기 창으로 올린다
  const chooser = page.waitForEvent("filechooser");
  await page.getByRole("button", { name: "PDF 등록" }).click();
  await (await chooser).setFiles({ name: "text-digital.pdf", mimeType: "application/pdf", buffer: pdf("text-digital.pdf") });
  await expect(page.getByRole("status").filter({ hasText: `이미 등록된 논문입니다: ${title}` })).toBeVisible();
  // 단추로 올릴 때도 가운데 받침이 떠서 결과를 보인다 (끄는 중이 아니므로 창 테두리는 없다)
  await expect(overlayDrop).toHaveAttribute("data-phase", "failed");
  await expect(page.locator(".drop-overlay")).not.toHaveAttribute("data-dragging");
  await expect(page.locator(".drop-overlay")).toHaveCount(0, { timeout: 10_000 });

  // 3) 이미 등록됐다는 안내의 바로가기로 그 논문을 연다
  await page.getByRole("button", { name: "기존 논문 열기" }).click();
  await expect(page).toHaveURL(new RegExp(`/reader/${paperId}\\?version=`));
});

test("서재가 비면 표 자리에 PDF 받침을 두고, 첫 논문이 등록되면 결과를 보인 뒤 표로 바뀐다", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "dpr-1", "올리기는 DPR과 무관하다");
  const { paperId } = (await uploadAll(page))["text-digital.pdf"];
  const stored = await (await page.request.get(`/api/v1/papers/${paperId}`)).json();
  // 추출 중이면 서재가 목록을 다시 받아(빈 목록) 표가 사라지므로, 응답의 논문은 추출이 끝난 상태로 둔다
  const paper = { ...stored, current_version: { ...stored.current_version, status: "INDEXED" } };
  // 빈 서재는 목록을, 첫 등록은 올리기 응답을 바꿔 만든다(공유 E2E 데이터에 논문을 더하지 않는다)
  await page.route("**/api/v1/papers", (route) =>
    route.request().method() === "GET" ? route.fulfill({ json: { papers: [] } }) : route.fulfill({ status: 201, json: paper }),
  );
  await page.goto("/");
  const zone = page.getByRole("button", { name: /^PDF 등록: 여기에 끌어다 놓거나/ });
  await expect(zone).toHaveAttribute("data-phase", "idle");
  await expect(zone.locator(".file-drop-title")).toHaveText("PDF를 끌어다 놓으세요");
  await expect(page.locator(".shelf-table")).toHaveCount(0);

  // 받침을 누르면 파일 고르기 창이 열린다. 창 전체 받침(.drop-overlay)은 띄우지 않고 이 받침이 결과를 보인다
  const chooser = page.waitForEvent("filechooser");
  await zone.click();
  await (await chooser).setFiles({ name: "text-digital.pdf", mimeType: "application/pdf", buffer: pdf("text-digital.pdf") });
  await expect(zone).toHaveAttribute("data-phase", "done");
  await expect(zone.locator(".file-drop-title")).toHaveText("서재에 등록했습니다");
  await expect(zone.locator(".file-drop-detail")).toHaveText(paper.title);
  // 등록 안내에 마우스를 올려 두면 남은 시간 줄이 멈춰, 받침이 사라질 때까지 안내가 남는다
  await page.locator(".toast").filter({ hasText: `등록됨: ${paper.title}` }).hover();
  await expect(page.locator(".drop-overlay")).toHaveCount(0);
  await expect(row(page, paperId)).toBeVisible({ timeout: 10_000 });
  await expect(zone).toHaveCount(0);

  // 등록 안내의 바로가기로 방금 올린 논문을 연다
  await page.getByRole("button", { name: "논문 열기", exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`/reader/${paperId}\\?version=`));
});

test("논문을 열면 마지막 열람이 오늘이 되고 맨 위로 온다. 주석·대화 개수는 서버의 수다", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "dpr-1", "서재 표는 DPR과 무관하다");
  const uploaded = await uploadAll(page);
  for (const name of ["text-mixed.pdf", "text-references.pdf"] as const) {
    await page.goto("/");
    await row(page, uploaded[name].paperId).locator(".paper-open").click();
    await expect(page).toHaveURL(new RegExp(`/reader/${uploaded[name].paperId}\\?version=`));
    await expect(page.locator('.page[data-page-number="1"]')).toBeAttached();
    await page.getByRole("button", { name: "서재로 돌아가기" }).click();
  }
  await expect(page.locator(".shelf-table")).toBeVisible();
  const first = page.locator(".shelf-table tbody tr").first();
  await expect(first).toHaveAttribute("data-paper-id", uploaded["text-references.pdf"].paperId);
  await expect(page.locator(".shelf-table tbody tr").nth(1)).toHaveAttribute("data-paper-id", uploaded["text-mixed.pdf"].paperId);
  // 마지막 열람은 답변·주석 목록과 같은 짧은 시각이다(방금 연 논문이므로 "방금"이나 몇 분 전)
  await expect(first.locator("td").nth(6)).toHaveText(/^(방금|\d+분 전)$/);
  expect(await first.locator("td").nth(6).locator("time").getAttribute("datetime")).toMatch(/^\d{4}-\d{2}-\d{2}T/);
  // 제목 곁의 썸네일은 그 논문의 첫 쪽을 그리고, 제목 아래에는 쪽 수가 든 한 줄이 있다
  await expect.poll(() => first.locator(".paper-thumb img").evaluate((img: HTMLImageElement) => img.naturalWidth)).toBeGreaterThan(0);
  await expect(first.locator(".paper-meta")).toHaveText(/\d+쪽$/);

  for (const name of FILES) {
    const paper = await (await page.request.get(`/api/v1/papers/${uploaded[name].paperId}`)).json();
    const cells = row(page, uploaded[name].paperId).locator("td");
    await expect(cells.nth(3)).toHaveText(paper.annotation_count ? String(paper.annotation_count) : "—");
    await expect(cells.nth(4)).toHaveText(paper.conversation_count ? String(paper.conversation_count) : "—");
  }
});

test("논문 삭제: 확인 창에서 취소하면 그대로, 확인하면 서재와 서버에서 모두 지운다(되돌릴 수 없다고 알린다)", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "dpr-1", "서재 표는 DPR과 무관하다");
  // 실행마다 다른 바이트라야 중복 등록이 아니다: 합성 PDF 끝에 주석 한 줄을 붙인다
  const bytes = Buffer.concat([pdf("text-mixed.pdf"), Buffer.from(`\n% delete test ${Date.now()}\n`)]);
  const uploaded = await uploadPdf(page, bytes, "delete-me.pdf");
  const status = async () => (await (await page.request.get(`/api/v1/papers/${uploaded.paperId}`)).json()).current_version.status;
  await expect.poll(status, { timeout: 60_000 }).not.toMatch(/^(READY_TO_READ|PARSING)$/); // 추출 중에는 지울 수 없다
  await page.goto("/");
  const target = row(page, uploaded.paperId);
  const title = await target.locator(".paper-open").innerText();
  const remove = target.getByRole("button", { name: `${title} 삭제` });

  page.once("dialog", (dialog) => void dialog.dismiss());
  await remove.click();
  await expect(target).toBeVisible();
  expect((await page.request.get(`/api/v1/papers/${uploaded.paperId}`)).status()).toBe(200);

  page.once("dialog", (dialog) => {
    expect(dialog.message()).toContain(`"${title}" 논문을 지울까요?`);
    expect(dialog.message()).toContain("되돌릴 수 없습니다");
    void dialog.accept();
  });
  await remove.click();
  await expect(target).toHaveCount(0);
  await expect(page.getByRole("status").filter({ hasText: `삭제됨: ${title}` })).toBeVisible();
  // 성공 안내는 남은 시간 줄이 다 줄면 스스로 닫힌다
  await expect(page.getByRole("status").filter({ hasText: `삭제됨: ${title}` })).toHaveCount(0, { timeout: 10_000 });
  expect((await page.request.get(`/api/v1/papers/${uploaded.paperId}`)).status()).toBe(404);
  await page.reload();
  await expect(row(page, uploaded.paperId)).toHaveCount(0);
});

test("페이지 나누기: 페이지당 편 수를 고르면(새로고침해도 남는다) 표가 그만큼씩 나뉘고, 페이지를 옮기며, 거르면 첫 페이지로 돌아간다", async ({ page }, testInfo) => {
  // 2026-11-25 사용자 요청
  test.skip(testInfo.project.name !== "dpr-1", "서재 표는 DPR과 무관하다");
  const { paperId } = (await uploadAll(page))["text-digital.pdf"];
  const stored = await (await page.request.get(`/api/v1/papers/${paperId}`)).json();
  // 논문 12편의 서재를 목록 응답으로 만든다(공유 E2E 데이터의 논문 수에 기대지 않는다). 9번째부터는 태그가 붙어 있다
  const name = (index: number) => `Paged paper ${String(index).padStart(2, "0")}`;
  const papers = Array.from({ length: 12 }, (_, index) => ({
    ...stored,
    paper_id: `00000000-0000-4000-8000-${String(index + 1).padStart(12, "0")}`,
    title: name(index + 1),
    tags: index >= 8 ? ["Later"] : [],
    current_version: { ...stored.current_version, status: "INDEXED", status_reason: null },
  }));
  await page.route("**/api/v1/papers", (route) => (route.request().method() === "GET" ? route.fulfill({ json: { papers } }) : route.continue()));
  await page.goto("/");
  const rows = page.locator(".shelf-table tbody tr");
  const titles = () => rows.locator(".paper-open").allInnerTexts();
  const range = page.getByTestId("pager-range");
  const pager = page.getByRole("navigation", { name: "페이지 이동" });
  const size = page.getByLabel("페이지당 논문 수");

  // 1) 시험은 페이지당 100편으로 시작한다(playwright.config.ts): 한 페이지라 페이지 단추가 없다
  await expect(rows).toHaveCount(12);
  await expect(size).toHaveValue("100");
  await expect(range).toHaveText("1–12 / 12편");
  await expect(pager).toHaveCount(0);

  // 2) 5편씩: 세 페이지로 나뉘고 첫 페이지에서는 이전이 막힌다
  await size.selectOption("5");
  await expect(rows).toHaveCount(5);
  await expect(range).toHaveText("1–5 / 12편");
  await expect(pager.getByRole("button", { name: /^\d+페이지$/ })).toHaveCount(3);
  await expect(pager.getByRole("button", { name: "1페이지" })).toHaveAttribute("aria-current", "page");
  await expect(pager.getByRole("button", { name: "이전 페이지" })).toBeDisabled();
  expect(await titles()).toEqual([1, 2, 3, 4, 5].map(name));

  // 3) 다음·번호로 옮긴다. 마지막 페이지는 남은 두 편이고 다음이 막힌다. 머리의 편 수는 서재 전체다
  await pager.getByRole("button", { name: "다음 페이지" }).click();
  await expect(range).toHaveText("6–10 / 12편");
  expect(await titles()).toEqual([6, 7, 8, 9, 10].map(name));
  await pager.getByRole("button", { name: "3페이지" }).click();
  await expect(rows).toHaveCount(2);
  await expect(range).toHaveText("11–12 / 12편");
  await expect(pager.getByRole("button", { name: "3페이지" })).toHaveAttribute("aria-current", "page");
  await expect(pager.getByRole("button", { name: "다음 페이지" })).toBeDisabled();
  await expect(page.getByTestId("shelf-count")).toHaveText("12편");

  // 4) 편 수를 바꾸면 보던 첫 논문(11번째)이 든 페이지로 간다. 새로고침해도 편 수가 남는다(페이지는 처음부터)
  await size.selectOption("10");
  await expect(range).toHaveText("11–12 / 12편");
  await expect(pager.getByRole("button", { name: "2페이지" })).toHaveAttribute("aria-current", "page");
  await page.reload();
  await expect(size).toHaveValue("10");
  await expect(rows).toHaveCount(10);
  await expect(range).toHaveText("1–10 / 12편");

  // 5) 2페이지에서 태그로 거르면 첫 페이지로 돌아가고, 범위는 거른 논문 수다(한 페이지라 페이지 단추가 없다)
  await pager.getByRole("button", { name: "2페이지" }).click();
  await expect(rows).toHaveCount(2);
  await rows.first().getByRole("button", { name: "Later", exact: true }).click();
  await expect(rows).toHaveCount(4);
  expect(await titles()).toEqual([9, 10, 11, 12].map(name));
  await expect(range).toHaveText("1–4 / 4편");
  await expect(page.getByTestId("shelf-count")).toHaveText("4 / 12편");
  await expect(pager).toHaveCount(0);
});
