/**
 * 실제 논문 E2E (로컬 전용, 2026-10-14 사용자 요청: "tests/e2e_papers에 실제 논문 PDF 파일 있는데 이거 기반으로 테스트 진행해줘").
 * tests/e2e_papers/의 PDF는 저작권 때문에 저장소에 넣지 않는다(.gitignore). 폴더가 있고 PAPERLOOM_REAL_PAPERS=1일 때만 돈다
 * (기본 실행·CI는 건너뛴다). 올린 논문은 끝나면 지워 E2E 데이터 폴더(var/e2e)에 남기지 않는다.
 * 실행(apps/web): PAPERLOOM_REAL_PAPERS=1 npx playwright test e2e/real-papers.spec.ts --project=dpr-1
 * 본문 추출 성질은 pytest -m real_papers(tests/real_papers)가 본다. 여기서는 브라우저 쪽(PDF.js·서재·선택)을 본다.
 */
import { existsSync, readdirSync, readFileSync } from "node:fs";

import { expect, type Page, test } from "@playwright/test";

import { fakeRuns, menuItem, showPage, type Uploaded } from "./fixture";

const DIR = new URL("../../../tests/e2e_papers/", import.meta.url);
const NAMES = existsSync(DIR) ? readdirSync(DIR).filter((name) => name.toLowerCase().endsWith(".pdf")).sort() : [];
const SCHEDULABILITY = "Schedulability Analysis of Global Scheduling for Multicore Systems With Shared Caches.pdf"; // 3B2 수식 글꼴
const PREDICTING = "Predicting Inter-Thread Cache Contention on a Chip Multi-Processor Architecture.pdf"; // Word 수식(Type3)
const LIU_LAYLAND = "Scheduling Algorithms for Multiprogramming in a Hard-Real-Time Environment.pdf"; // 글꼴에 유니코드가 없다

test.skip(!process.env.PAPERLOOM_REAL_PAPERS || NAMES.length === 0, "PAPERLOOM_REAL_PAPERS=1이고 tests/e2e_papers에 논문이 있을 때만 돈다");

const uploaded = new Map<string, Uploaded>();

/** 논문을 올리고 본문 추출이 끝날 때까지 기다린다. 이미 올렸으면(앞 실행이 지우지 못함) 그 논문을 쓴다. */
async function upload(page: Page, name: string): Promise<Uploaded> {
  const done = uploaded.get(name);
  if (done) return done;
  const response = await page.request.post("/api/v1/papers", {
    data: readFileSync(new URL(name, DIR)),
    headers: { "Content-Type": "application/pdf", "X-Paperloom-Filename": encodeURIComponent(name) },
  });
  expect([201, 409]).toContain(response.status());
  const body = await response.json();
  const paperId: string = response.status() === 201 ? body.paper_id : body.details.paper_id;
  let versionId = "";
  await expect
    .poll(
      async () => {
        const paper = await (await page.request.get(`/api/v1/papers/${paperId}`)).json();
        versionId = paper.current_version.version_id;
        return paper.current_version.status;
      },
      { timeout: 120_000 },
    )
    .not.toMatch(/READY_TO_READ|PARSING/);
  const result = { paperId, versionId };
  uploaded.set(name, result);
  return result;
}

test.afterAll(async ({ playwright }, testInfo) => {
  const api = await playwright.request.newContext({ baseURL: testInfo.project.use.baseURL });
  for (const { paperId } of uploaded.values()) await api.delete(`/api/v1/papers/${paperId}`);
  await api.dispose();
  uploaded.clear();
});

test("모든 실제 논문을 올리면 본문을 추출하고, Reader가 첫 쪽의 글자 층까지 그린다", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "dpr-1", "DPR과 무관하다");
  test.setTimeout(30 * 60_000);
  const failed: string[] = [];
  for (const name of NAMES) {
    const { paperId, versionId } = await upload(page, name);
    await page.goto(`/reader/${paperId}?version=${versionId}`);
    try {
      await expect(page.locator('.page[data-page-number="1"] .textLayer span').first()).toBeAttached({ timeout: 30_000 });
    } catch {
      failed.push(name);
    }
  }
  expect(failed).toEqual([]);
});

test("서재는 수식 기호만 못 읽은 논문과 글을 거의 못 읽는 논문을 나눠 알린다", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "dpr-1", "DPR과 무관하다");
  const labels: [string, string][] = [
    [SCHEDULABILITY, "검색 가능"], // 3B2 수식 기호를 되찾아 모든 쪽 정상
    [PREDICTING, "검색 가능 · 일부 기호를 읽지 못함"],
    [LIU_LAYLAND, "검색 불가 · 글자를 읽을 수 없음(글꼴에 문자 정보 없음)"], // 쪽마다 글자 96–100%를 못 읽는다(첫 실행은 "일부 쪽만 검색 가능")
  ];
  const present = labels.filter(([name]) => NAMES.includes(name));
  test.skip(present.length === 0, "해당 논문이 없다");
  for (const [name] of present) await upload(page, name);
  await page.goto("/");
  for (const [name, label] of present) {
    const { paperId } = uploaded.get(name)!;
    await expect(page.locator(`tr[data-paper-id="${paperId}"] td[data-status] .tag`)).toHaveText(label);
  }
});

/** 그 쪽에서 글(contains)이 든 추출 문단 자리의 text layer 글을 고르고 메뉴가 뜰 때까지 기다린다. */
async function selectParagraph(page: Page, versionId: string, pageIndex: number, contains: string) {
  const { blocks } = await (await page.request.get(`/api/v1/versions/${versionId}/pages/${pageIndex}`)).json();
  const block = blocks.find((item: { text: string }) => item.text.includes(contains));
  expect(block, contains).toBeTruthy();
  const regions: number[][] = block.regions;
  const box = [Math.min(...regions.map((r) => r[0])), Math.min(...regions.map((r) => r[1])), Math.max(...regions.map((r) => r[2])), Math.max(...regions.map((r) => r[3]))];
  await showPage(page, pageIndex);
  await expect(page.locator(`.page[data-page-number="${pageIndex + 1}"] .textLayer span`).first()).toBeAttached();
  await page.evaluate(
    ({ pageIndex, box: [u0, v0, u1, v1] }) => {
      const pageDiv = document.querySelector(`.page[data-page-number="${pageIndex + 1}"]`)!;
      const frame = pageDiv.getBoundingClientRect();
      const spans = [...pageDiv.querySelectorAll(".textLayer span")].filter((span) => {
        const rect = span.getBoundingClientRect();
        const u = ((rect.left + rect.right) / 2 - frame.left) / frame.width;
        const v = ((rect.top + rect.bottom) / 2 - frame.top) / frame.height;
        return rect.height > 0 && span.firstChild instanceof Text && u >= u0 && u <= u1 && v >= v0 && v <= v1;
      });
      const range = document.createRange();
      range.setStart(spans[0].firstChild!, 0);
      const last = spans.at(-1)!.firstChild!;
      range.setEnd(last, last.textContent!.length);
      document.getSelection()!.removeAllRanges();
      document.getSelection()!.addRange(range);
    },
    { pageIndex, box },
  );
  await expect(page.locator(".selection-menu")).toBeVisible();
}

test("수식 기호를 읽지 못한 문단을 골라 설명을 물으면 원문 이미지를 함께 보내고, 고른 글의 제어 문자는 뺀다", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "dpr-1", "대화 흐름은 DPR과 무관하다");
  const cases: [string, number, string][] = [
    [PREDICTING, 3, "denote the total cache size"], // 4쪽: Type3 수식 기호를 유니코드로 바꾸지 못한 문단
    [SCHEDULABILITY, 2, "to denote the set of tasks"], // 3쪽: 브라우저 글자 층은 hp(k)를 hpðkÞ로 준다
  ];
  const present = cases.filter(([name]) => NAMES.includes(name));
  test.skip(present.length === 0, "해당 논문이 없다");
  for (const [name, pageIndex, contains] of present) {
    const { paperId, versionId } = await upload(page, name);
    await page.goto(`/reader/${paperId}?version=${versionId}`);
    await selectParagraph(page, versionId, pageIndex, contains);
    const runsBefore = fakeRuns().length;
    await menuItem(page, "설명").click();
    await expect.poll(() => fakeRuns().length, { timeout: 30_000 }).toBeGreaterThan(runsBefore);
    const run = fakeRuns().slice(runsBefore)[0];
    expect(run.message.message.content.map((part) => part.type), name).toContain("image");
    // 첫 실행에서 찾음: Type3 수식 글꼴의 글자 층이 \x00 \x01 같은 제어 문자를 주어 고른 글에 그대로 실려 갔다
    const sent = run.message.message.content.map((part) => part.text ?? "").join("");
    expect(sent.replace(/[\n\t]/g, ""), name).not.toMatch(/[\p{Cc}\p{Co}]/u);
  }
});
