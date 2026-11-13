/**
 * PDF로 내보내기 (2026-11-13 사용자 요청): 머리의 내려받기 단추로 창을 열어 하이라이트·주석·설명·AI 질문 가운데 넣을 것을
 * 고르고, 원본 PDF 뒤에 그것을 PDF 표준 주석으로 붙인 파일을 논문 제목으로 내려받는다.
 * 다른 시험이 쓰지 않는 text-tight.pdf를 쓴다(E2E 데이터 폴더는 실행 사이에 남으므로 시작할 때 주석·대화를 비운다).
 */
import { readFileSync } from "node:fs";

import { expect, type Page, test } from "@playwright/test";

import { clearAnnotations, clearThreads, FIXTURE_DIR, openFixture, uploadPdf } from "./fixture";

const FILE = "text-tight.pdf";
const PDF = readFileSync(new URL(FILE, FIXTURE_DIR));

async function anchorAt(page: Page, versionId: string, v: number, quote: string): Promise<string> {
  const body = { schema_version: "anchor.v1", version_id: versionId, page_index: 0, quads: [[0.1, v, 0.5, v, 0.5, v + 0.02, 0.1, v + 0.02]], quote };
  const response = await page.request.post("/api/v1/anchors", { data: body });
  expect(response.status()).toBe(201);
  return (await response.json()).anchor_id;
}

/** 브리지가 한 차례를 끝낸 것처럼 답을 저장하고 원문 위 대화로 남긴다 */
async function thread(page: Page, paperId: string, anchorId: string, kind: "explain" | "ask", prompt: string, markdown: string) {
  const packet = await (await page.request.post("/api/v1/context-packets", { data: { intent: kind, question: prompt, anchors: [{ anchor_id: anchorId }] } })).json();
  await page.request.patch(`/api/v1/context-packets/${packet.packet_id}`, { data: { status: "HANDED_OFF", handoff_method: "claude_code" } });
  const session = crypto.randomUUID();
  expect((await page.request.post(`/api/v1/context-packets/${packet.packet_id}/answers`, { data: { markdown, prompt, session_id: session } })).status()).toBe(201);
  const saved = await page.request.post("/api/v1/chat-threads", { data: { session_id: session, paper_id: paperId, anchor_id: anchorId, kind, title: prompt } });
  expect(saved.status()).toBe(201);
}

test("PDF로 내보내기: 넣을 것을 골라 원본에 PDF 메모로 붙인 파일을 논문 제목으로 내려받는다", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "dpr-1", "내려받는 파일은 화면 배율과 무관하다");
  const { paperId, versionId } = await uploadPdf(page, PDF, FILE);
  await clearAnnotations(page, versionId);
  await clearThreads(page, paperId);
  // 대화의 문맥은 추출한 본문으로 만든다
  await expect.poll(async () => (await (await page.request.get(`/api/v1/versions/${versionId}`)).json()).status, { timeout: 30_000 }).toMatch(/INDEXED|PARTIAL/);

  const first = await anchorAt(page, versionId, 0.1, "multiprocessor");
  const second = await anchorAt(page, versionId, 0.2, "real time missions");
  await page.request.post("/api/v1/annotations", { data: { anchor_id: first, comment: "핵심 가정", color: "c2" } });
  await page.request.post("/api/v1/annotations", { data: { anchor_id: second, comment: "따로 단 메모" } });
  await thread(page, paperId, first, "explain", "고른 부분을 쉽게 설명해 주세요.", "여러 처리기를 쓰는 구조입니다.");
  await thread(page, paperId, second, "ask", "어떤 임무인가요?", "자율 제어 같은 임무입니다.");
  const title: string = (await (await page.request.get(`/api/v1/papers/${paperId}`)).json()).title;

  await openFixture(page, PDF, FILE);
  await page.getByRole("button", { name: "PDF로 내보내기" }).click();
  const dialog = page.getByRole("dialog", { name: "PDF로 내보내기" });
  // 처음에는 모두 고른다. 주석은 메모가 있는 주석이라 하이라이트에 단 메모도 센다
  for (const [label, count] of [["하이라이트", "1"], ["주석", "2"], ["설명", "1"], ["AI 질문", "1"]]) {
    const row = dialog.locator(".pdf-export-check").filter({ hasText: label });
    await expect(row.getByRole("checkbox")).toBeChecked();
    await expect(row.locator(".pdf-export-count")).toHaveText(count);
  }

  await dialog.locator(".pdf-export-check").filter({ hasText: "설명" }).getByRole("checkbox").uncheck();
  const download = page.waitForEvent("download");
  await dialog.getByRole("button", { name: "PDF 내려받기" }).click();
  const file = await download;
  await expect(dialog).toHaveCount(0);

  expect(file.suggestedFilename()).toBe(`${title}.pdf`);
  const bytes = readFileSync(await file.path());
  const original = await (await page.request.get(`/api/v1/versions/${versionId}/pdf`)).body();
  expect(bytes.subarray(0, original.length).equals(original)).toBe(true); // 원본은 그대로, 뒤에 덧붙인다
  const added = bytes.subarray(original.length).toString("latin1");
  expect(added.match(/\/Subtype \/Highlight/g)).toHaveLength(1);
  expect(added.match(/\/Subtype \/Text/g)).toHaveLength(2); // 하이라이트의 메모는 하이라이트에 들어가고, 따로 단 메모와 AI 질문만 아이콘이다

  // 모두 빼면 내려받을 수 없다
  await page.getByRole("button", { name: "PDF로 내보내기" }).click();
  for (const box of await dialog.getByRole("checkbox").all()) await box.uncheck();
  await expect(dialog.getByRole("button", { name: "PDF 내려받기" })).toBeDisabled();

  await clearThreads(page, paperId); // 다른 시험의 답변 화면에 남지 않게 한다
});
