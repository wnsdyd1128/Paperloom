/**
 * Wiki로 내보내기 (docs/integration/paperloom): Reader·서재에서 창을 열고, 미리보기를 거쳐 outbox에 bundle을 쓰고, 파일의 해시와
 * 내용을 디스크에서 확인하고, bundle의 Reader 링크로 돌아오고, 기록 화면에서 본다. LLM Wiki 수신은 tests/contract가 맡는다.
 */
import { createHash } from "node:crypto";
import { mkdirSync, readdirSync, readFileSync, rmSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { expect, type Page, test } from "@playwright/test";

import { FIXTURE_DIR, GEOMETRY_PDF, openFixture, uploadPdf } from "./fixture";

const OUTBOX = fileURLToPath(new URL("../../../var/e2e/outbox/", import.meta.url));
const DIGITAL_PDF = readFileSync(new URL("text-digital.pdf", FIXTURE_DIR));
const QUAD = [0.1, 0.1, 0.5, 0.1, 0.5, 0.12, 0.1, 0.12];

type Manifest = { bundle_id: string; schema_version: string; files: { path: string; sha256: string; size_bytes: number }[] };

/** 저장된 위치. E2E 데이터 폴더는 실행 사이에 남으므로 이번 시험의 글로 찾는다. */
async function makeAnchor(page: Page, versionId: string, quote: string, comment?: string): Promise<string> {
  const response = await page.request.post("/api/v1/anchors", {
    data: { schema_version: "anchor.v1", kind: "text", version_id: versionId, page_index: 0, quads: [QUAD], quote, display_quote: null, prefix: "", suffix: "" },
  });
  expect(response.status()).toBe(201);
  const { anchor_id: anchorId } = await response.json();
  if (comment) expect((await page.request.post("/api/v1/annotations", { data: { anchor_id: anchorId, comment } })).status()).toBe(201);
  return anchorId;
}

function exportDialog(page: Page) {
  return page.getByRole("dialog", { name: "Wiki로 내보내기" });
}

function onlyBundle(): string {
  const names = readdirSync(OUTBOX);
  expect(names).toHaveLength(1);
  expect(names[0]).toMatch(/^bundle_[0-9a-f-]{36}$/);
  return `${OUTBOX}${names[0]}/`;
}

function readManifest(folder: string): Manifest {
  const manifest: Manifest = JSON.parse(readFileSync(`${folder}manifest.json`, "utf-8"));
  for (const file of manifest.files) {
    const bytes = readFileSync(`${folder}${file.path}`);
    expect(bytes.length, file.path).toBe(file.size_bytes);
    expect(createHash("sha256").update(bytes).digest("hex"), file.path).toBe(file.sha256);
  }
  return manifest;
}

test.beforeEach(() => {
  rmSync(OUTBOX, { recursive: true, force: true });
  mkdirSync(OUTBOX, { recursive: true });
});

test("Reader에서 위치·메모·제안을 고르고 미리본 뒤 bundle을 쓴다", async ({ page }) => {
  const quote = `내보낼 인용 ${Date.now()}`;
  const fixture = await openFixture(page);
  const anchorId = await makeAnchor(page, fixture.versionId, quote, "내보낼 메모");
  await page.reload();

  await page.getByRole("button", { name: "Wiki로 내보내기" }).click();
  const dialog = exportDialog(page);
  await expect(dialog.getByText("보낼 폴더")).toBeVisible();
  const row = dialog.getByRole("region", { name: "넣을 위치" }).getByRole("listitem").filter({ hasText: quote });
  await expect(row.getByText("메모")).toBeVisible();
  await expect(row.getByRole("checkbox")).not.toBeChecked(); // 처음에는 아무것도 고르지 않는다
  await row.getByRole("checkbox").check();

  // 빈 제안은 미리보기로 넘어가지 못하고 그 칸을 표시한다
  await dialog.getByRole("button", { name: "제안 추가" }).click();
  await dialog.getByRole("button", { name: "미리보기" }).click();
  await expect(dialog.getByRole("alert")).toContainText("표시한 칸");
  const title = dialog.getByRole("textbox", { name: "제목" });
  await expect(title).toHaveAttribute("aria-invalid", "true");
  await title.fill("SCP의 개선 조건");
  await dialog.getByRole("textbox", { name: "본문 (Markdown)" }).fill("# 제안\n\n본문입니다.\n");
  await dialog.getByRole("group", { name: "제안 1의 근거" }).getByRole("listitem").filter({ hasText: quote }).getByRole("checkbox").check();

  await dialog.getByRole("button", { name: "미리보기" }).click();
  await expect(dialog.getByRole("cell", { name: "manifest.json" })).toBeVisible();
  await expect(dialog.getByText("원본 PDF는 넣지 않습니다.")).toBeVisible();
  expect(readdirSync(OUTBOX)).toEqual([]); // 미리보기는 아무것도 쓰지 않는다

  // 돌아가도 고른 것이 그대로다
  await dialog.getByRole("button", { name: "돌아가기" }).click();
  await expect(dialog.getByRole("textbox", { name: "제목" })).toHaveValue("SCP의 개선 조건");
  await dialog.getByRole("button", { name: "미리보기" }).click();
  await dialog.getByRole("button", { name: "내보내기", exact: true }).click();

  await expect(dialog.getByRole("status")).toContainText("Wiki로 내보냈습니다");
  const folder = onlyBundle();
  const manifest = readManifest(folder);
  expect(manifest.schema_version).toBe("paperloom-bundle.v1.1"); // 기본은 고른 위치가 있는 쪽의 추출문을 싣는다
  expect(manifest.files.map((file) => file.path)).toContain(`texts/${fixture.versionId}.json`);
  const [source] = JSON.parse(readFileSync(`${folder}sources.json`, "utf-8"));
  const [anchor] = JSON.parse(readFileSync(`${folder}anchors.json`, "utf-8"));
  expect(source.version_id).toBe(fixture.versionId);
  expect(source.reader_url).toBe(`http://127.0.0.1:8791/reader/${fixture.paperId}?version=${fixture.versionId}`);
  expect([anchor.anchor_id, anchor.quote, anchor.comment]).toEqual([anchorId, quote, "내보낼 메모"]);
  const proposalPath = manifest.files.map((file) => file.path).find((path) => path.startsWith("proposals/"))!;
  const proposal = JSON.parse(readFileSync(`${folder}${proposalPath}`, "utf-8"));
  expect(proposal.anchor_refs).toEqual([anchor.anchor_ref]);
  expect(readFileSync(`${folder}${proposal.content_file}`, "utf-8")).toBe("# 제안\n\n본문입니다.\n");

  // 기록 화면
  await dialog.getByRole("button", { name: "기록 보기" }).click();
  await expect(page).toHaveURL(/\/bundles$/);
  const line = page.locator(`tr[data-bundle-id="${manifest.bundle_id}"]`);
  await expect(line).toContainText("written");
  await line.getByRole("button").click();
  const detail = page.getByRole("region", { name: "bundle 상세" });
  await expect(detail.getByText(manifest.bundle_id)).toBeVisible();
  await expect(detail.getByRole("cell", { name: "anchors.json" })).toBeVisible();

  // 지우면 기록은 남고 없다고 알린다 (F-06)
  rmSync(OUTBOX, { recursive: true });
  mkdirSync(OUTBOX);
  await page.reload();
  await expect(page.locator(`tr[data-bundle-id="${manifest.bundle_id}"]`)).toContainText("outbox에 없음");

  // Wiki 노트의 Reader 링크로 그 판본·위치가 열린다 (AC-07)
  await page.goto(anchor.reader_url);
  await expect(page).toHaveURL(new RegExp(`version=${fixture.versionId}&anchor=${anchorId}`));
  await expect(page.locator('.page[data-page-number="1"] > .annotation-overlay > .quad-mark.is-focused')).toHaveCount(1);
});

test("서재에서 논문 여러 편을 골라 내보낸다", async ({ page }) => {
  const first = await uploadPdf(page, GEOMETRY_PDF, "geometry-matrix.pdf");
  const second = await uploadPdf(page, DIGITAL_PDF, "text-digital.pdf");
  await page.goto("/");

  const button = page.getByRole("button", { name: /Wiki로 내보내기/ });
  await expect(button).toBeDisabled(); // 고르기 전
  await page.locator(`tr[data-paper-id="${first.paperId}"] input[type="checkbox"]`).check();
  await page.locator(`tr[data-paper-id="${second.paperId}"] input[type="checkbox"]`).check();
  await expect(button).toHaveText("Wiki로 내보내기 (2편)");
  await button.click();

  const dialog = exportDialog(page);
  await expect(dialog.locator(".export-card")).toHaveCount(2);
  await dialog.locator(`.export-card[data-version-id="${first.versionId}"]`).getByRole("button", { name: /목록에서 빼기/ }).click();
  await expect(dialog.locator(".export-card")).toHaveCount(1);

  await dialog.getByRole("button", { name: "미리보기" }).click();
  await dialog.getByRole("button", { name: "내보내기", exact: true }).click();
  await expect(dialog.getByRole("status")).toContainText("파일 3개");

  const folder = onlyBundle();
  readManifest(folder);
  expect(JSON.parse(readFileSync(`${folder}sources.json`, "utf-8")).map((source: { version_id: string }) => source.version_id)).toEqual([second.versionId]);
  expect(readdirSync(folder).sort()).toEqual(["anchors.json", "manifest.json", "sources.json"]);
});

test("고른 답변을 넣고 인용한 위치를 자동으로 더한다", async ({ page }) => {
  const quote = `답변이 인용한 글 ${Date.now()}`;
  const fixture = await openFixture(page);
  const anchorId = await makeAnchor(page, fixture.versionId, quote);
  const packet = await (await page.request.post("/api/v1/context-packets", { data: { intent: "ask", question: "질문", anchors: [{ anchor_id: anchorId }] } })).json();
  await page.request.patch(`/api/v1/context-packets/${packet.packet_id}`, { data: { status: "HANDED_OFF", handoff_method: "claude_code" } });
  const markdown = `답변 본문 ${quote} [근거 1].`;
  const answer = await (
    await page.request.post(`/api/v1/context-packets/${packet.packet_id}/answers`, {
      data: { markdown, prompt: `차례의 질문 ${quote}`, session_id: crypto.randomUUID() },
    })
  ).json();
  await page.reload();

  await page.getByRole("button", { name: "Wiki로 내보내기" }).click();
  const dialog = exportDialog(page);
  await dialog.getByRole("region", { name: "넣을 답변" }).getByRole("listitem").filter({ hasText: quote }).getByRole("checkbox").check();
  await dialog.getByRole("button", { name: "제안 추가" }).click();
  await dialog.getByRole("textbox", { name: "제목" }).fill("답변에서 만든 제안");
  await dialog.getByRole("button", { name: "고른 답변 본문 넣기" }).click();
  await expect(dialog.getByRole("textbox", { name: "본문 (Markdown)" })).toHaveValue(markdown);

  await dialog.getByRole("button", { name: "미리보기" }).click();
  await expect(dialog.getByRole("region", { name: "자동으로 더한 위치" })).toContainText(anchorId.slice(0, 8));
  await dialog.getByRole("button", { name: "내보내기", exact: true }).click();
  await expect(dialog.getByRole("status")).toContainText("Wiki로 내보냈습니다");

  const folder = onlyBundle();
  readManifest(folder);
  const text = readFileSync(`${folder}artifacts/answer-${answer.answer_id}.md`, "utf-8");
  expect(text).toContain("> 근거: [근거 1] = anc_1 (쪽 1)");
  expect(text).toContain(markdown);
});

test("outbox가 준비되지 않으면 내보내기를 막고 이유를 보인다", async ({ page }) => {
  await page.route("**/api/v1/health", async (route) => {
    const response = await route.fetch();
    await route.fulfill({ response, json: { ...(await response.json()), wiki_outbox: { status: "not_configured", path: null } } });
  });
  const fixture = await openFixture(page);

  const reader = page.getByRole("button", { name: "Wiki로 내보내기" });
  await expect(reader).toBeDisabled();
  await expect(reader).toHaveAttribute("title", /wiki\.outbox_path/);

  await page.goto("/");
  await page.locator(`tr[data-paper-id="${fixture.paperId}"] input[type="checkbox"]`).check();
  const library = page.getByRole("button", { name: /Wiki로 내보내기/ });
  await expect(library).toBeDisabled();
  await expect(library).toHaveAttribute("title", /wiki\.outbox_path/);
});

test("한도를 넘으면 내보내기를 끄고 무엇을 줄일지 알린다", async ({ page }) => {
  await openFixture(page);
  await page.getByRole("button", { name: "Wiki로 내보내기" }).click();
  const dialog = exportDialog(page);
  await page.route("**/api/v1/evidence-bundles/preview", async (route) => {
    const response = await route.fetch();
    const preview = await response.json();
    await route.fulfill({ response, json: { ...preview, warnings: [{ code: "over_limit", detail: "파일 70개" }] } });
  });

  await dialog.getByRole("button", { name: "미리보기" }).click();

  await expect(dialog.getByRole("region", { name: "경고" })).toContainText("이미지, 추출문 범위 순으로 줄이세요");
  await expect(dialog.getByRole("button", { name: "내보내기", exact: true })).toBeDisabled();
});

test("서재에서 21편을 고르면 막고 개수를 알린다", async ({ page }) => {
  await uploadPdf(page, GEOMETRY_PDF, "geometry-matrix.pdf");
  await page.route("**/api/v1/papers", async (route) => {
    const response = await route.fetch();
    const [paper] = (await response.json()).papers;
    const papers = Array.from({ length: 21 }, (_, index) => ({ ...paper, paper_id: `paper-${index}` }));
    await route.fulfill({ response, json: { papers } });
  });
  await page.goto("/");

  const boxes = page.locator('tr[data-paper-id] input[type="checkbox"]');
  await expect(boxes).toHaveCount(21);
  for (const box of await boxes.all()) await box.check();

  await expect(page.getByRole("button", { name: /Wiki로 내보내기/ })).toBeDisabled();
  await expect(page.getByRole("status").filter({ hasText: "지금 21편" })).toBeVisible();
});

test("서버가 거부한 이유를 창에 보이고 닫을 때 쓴 제안을 묻는다", async ({ page }) => {
  await openFixture(page);
  await page.getByRole("button", { name: "Wiki로 내보내기" }).click();
  const dialog = exportDialog(page);
  await page.route("**/api/v1/evidence-bundles/preview", (route) =>
    route.fulfill({ status: 503, json: { code: "OUTBOX_UNAVAILABLE", message: "m", request_id: "r", retryable: true } }),
  );
  await dialog.getByRole("button", { name: "미리보기" }).click();
  await expect(dialog.getByRole("alert")).toContainText("outbox 연결을 확인하세요");

  await dialog.getByRole("button", { name: "제안 추가" }).click();
  await dialog.getByRole("textbox", { name: "제목" }).fill("쓰던 제안");
  page.once("dialog", (question) => void question.dismiss());
  await page.keyboard.press("Escape");
  await expect(dialog).toBeVisible(); // 묻는 말에 취소하면 그대로다
  await expect(dialog.getByRole("textbox", { name: "제목" })).toHaveValue("쓰던 제안");
  page.once("dialog", (question) => void question.accept());
  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
});
