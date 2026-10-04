/**
 * Reader E2E 공용 도구: 합성 fixture(tests/fixtures/pdf-layout/geometry-matrix.*)를 올려 열고,
 * 표식을 선택하고, 저장된 quad를 다시 그린 표시가 글자와 얼마나 어긋나는지 잰다.
 */
import { existsSync, readFileSync } from "node:fs";

import { expect, type Page } from "@playwright/test";

export type Marker = { text: string; pdf_point: [number, number]; normalized: [number, number]; advance_width: number };
export type FixturePage = {
  page_index: number;
  name: string;
  rotation: number;
  user_unit: number;
  view_box: number[];
  markers: Marker[];
  /** 두 색 사각형 (W04a 영역 선택의 기준). normalized는 회전 전 [u0, v0, u1, v1] */
  region: { pdf_rect: number[]; normalized: number[]; colors: { left: number[]; right: number[] } };
};
export type Quad = number[];
export type Target = { label: string; pageIndex: number; texts: string[]; markers: Marker[] };
type Rect = { left: number; top: number; right: number; bottom: number };

export const FIXTURE_DIR = new URL("../../../tests/fixtures/pdf-layout/", import.meta.url);
export const EXPECTED: { title: string; font_size: number; pages: FixturePage[] } = JSON.parse(
  readFileSync(new URL("geometry-matrix.json", FIXTURE_DIR), "utf8"),
);
export const GEOMETRY_PDF = readFileSync(new URL("geometry-matrix.pdf", FIXTURE_DIR));

export const CSS_UNITS = 96 / 72;
export const MAX_REPROJECTION_ERROR_PX = 2;

// 한 줄 표식은 각각, 첫 쪽의 두 줄은 함께 선택해 줄별 quad도 확인한다.
export const TARGETS: Target[] = [
  ...EXPECTED.pages.flatMap((page) =>
    page.markers.map((marker) => ({
      label: `${page.name}: ${marker.text}`,
      pageIndex: page.page_index,
      texts: [marker.text],
      markers: [marker],
    })),
  ),
  {
    label: "plain: two lines",
    pageIndex: 0,
    texts: EXPECTED.pages[0].markers.map((marker) => marker.text),
    markers: EXPECTED.pages[0].markers,
  },
];

/** 가짜 Claude Code CLI가 받은 실행 기록 (playwright.config.ts의 FAKE_CLAUDE_LOG, tests/fixtures/fake_claude) */
const FAKE_LOG = new URL("../../../var/e2e-claude/fake-claude.jsonl", import.meta.url);
export type FakeRun = {
  args: string[];
  env: string[];
  /** --system-prompt-file의 내용 (U6: 설정의 답 언어·개인화가 붙는다) */
  system_prompt?: string;
  message: { message: { content: { type: string; text?: string }[] } };
};

export function fakeRuns(): FakeRun[] {
  return existsSync(FAKE_LOG) ? readFileSync(FAKE_LOG, "utf-8").split("\n").filter(Boolean).map((line) => JSON.parse(line)) : [];
}

export type Uploaded = { paperId: string; versionId: string };

/** PDF를 올린다. 이미 올린 같은 바이트면 그 논문을 쓴다(E2E 데이터 폴더는 실행 사이에 남는다). */
export async function uploadPdf(page: Page, pdf: Buffer, filename: string): Promise<Uploaded> {
  const upload = await page.request.post("/api/v1/papers", {
    data: pdf,
    headers: { "Content-Type": "application/pdf", "X-Paperloom-Filename": filename },
  });
  expect([201, 409]).toContain(upload.status()); // 이미 올렸으면 중복 응답
  const body = await upload.json();
  // fixture를 고치면 같은 제목의 이전 판이 데이터 폴더에 남으므로 제목이 아니라 ID로 연다.
  const paperId: string = upload.status() === 201 ? body.paper_id : body.details.paper_id;
  const paper = await (await page.request.get(`/api/v1/papers/${paperId}`)).json();
  return { paperId, versionId: paper.current_version.version_id };
}

/** fixture(기본은 좌표 fixture)를 올리고 Library에서 연다. */
export async function openFixture(
  page: Page,
  pdf: Buffer = GEOMETRY_PDF,
  filename = "geometry-matrix.pdf",
): Promise<Uploaded> {
  const uploaded = await uploadPdf(page, pdf, filename);
  await page.goto("/");
  await page.locator(`tr[data-paper-id="${uploaded.paperId}"] .paper-open`).click();
  await expect(page.locator('.page[data-page-number="1"] .textLayer span').first()).toBeAttached();
  return uploaded;
}

/** 머리의 배율 칸 (누르면 배율 목록과 회전이 나온다) */
export function zoomButton(page: Page) {
  return page.getByRole("button", { name: "배율", exact: true });
}

/** 배율 목록에서 고른다. zoom은 PDF.js scale(1 = 100%) */
export async function chooseZoom(page: Page, zoom: number) {
  await zoomButton(page).click();
  await page.getByRole("menuitemradio", { name: `${Math.round(zoom * 100)}%`, exact: true }).click();
  await expect(zoomButton(page)).toHaveAttribute("data-zoom", String(zoom));
}

export async function setView(page: Page, rotation: number, zoom: number) {
  await chooseZoom(page, zoom);
  for (let clicks = 0; clicks < 4 && (await zoomButton(page).getAttribute("data-rotation")) !== String(rotation); clicks++) {
    await zoomButton(page).click();
    await page.getByRole("menuitem", { name: /시계 방향으로 회전/ }).click();
  }
  await expect(zoomButton(page)).toHaveAttribute("data-rotation", String(rotation));
}

export async function showPage(page: Page, pageIndex: number) {
  const pageDiv = page.locator(`.page[data-page-number="${pageIndex + 1}"]`);
  await pageDiv.evaluate((element) => element.scrollIntoView({ block: "center", inline: "center" }));
  // PDF.js는 페이지를 다시 그리는 동안 text layer를 숨긴다 (PDFPageView.reset → textLayer.hide).
  await expect(pageDiv.locator(".textLayer:not([hidden]) span").first()).toBeVisible();
}

/** 선택이 PDF.js 다시 그리기와 겹쳐 다시 시도한 횟수 (검증 기록용). */
export const selectionStats = { retries: 0 };

/** 현재 선택을 쪽에 다시 그린 표시. 표시마다 정본 좌표 quad(data-quad)를 가진다. */
export function selectionMarks(page: Page, pageIndex: number) {
  return page.locator(`.page[data-page-number="${pageIndex + 1}"] > .quad-overlay > .quad-mark`);
}

/** 표식 텍스트를 선택하고, 앱이 쪽에 그린 선택 표시의 정규화 quad를 읽는다. */
export async function selectAndRead(page: Page, target: Target): Promise<Quad[]> {
  const marks = selectionMarks(page, target.pageIndex);
  for (let attempt = 1; ; attempt++) {
    await showPage(page, target.pageIndex);
    await applySelection(page, target);
    try {
      // 선택마다 쪽·줄 수·인용이 바뀌므로 이전 선택의 표시와 구분된다.
      await expect(marks).toHaveCount(target.texts.length, { timeout: 3000 });
      await expect(page.locator(".quad-overlay")).toHaveCount(1, { timeout: 3000 });
      await expect(page.locator(SELECTION_STATUS)).toContainText(target.texts[0], { timeout: 3000 });
      break;
    } catch (error) {
      // 선택 직후 PDF.js가 다시 그리기를 시작하면 선택한 텍스트가 숨겨져 선택이 무시될 수 있다.
      if (attempt === 3) throw error;
      selectionStats.retries++;
    }
  }
  return marks.evaluateAll((items) => items.map((item) => JSON.parse(item.getAttribute("data-quad")!)));
}

async function applySelection(page: Page, target: Target) {
  await page.evaluate(({ pageIndex, texts }) => {
    const pageDiv = document.querySelector(`.page[data-page-number="${pageIndex + 1}"]`)!;
    const spans = [...pageDiv.querySelectorAll(".textLayer span")].filter((span) => texts.includes(span.textContent ?? ""));
    if (spans.length !== texts.length) throw new Error(`표식 span을 찾지 못함: ${texts.join(" / ")}`);
    const range = document.createRange();
    range.setStart(spans[0].firstChild!, 0);
    const last = spans.at(-1)!.firstChild!;
    range.setEnd(last, last.textContent!.length);
    const selection = document.getSelection()!;
    selection.removeAllRanges();
    selection.addRange(range);
  }, target);
}

/** 지금 고른 것을 알리는 글 (화면 낭독기용, 화면에는 보이지 않는다): 쪽·줄 수·인용·추정 표기 */
export const SELECTION_STATUS = '[data-testid="selection-status"]';

/** 고른 글 곁의 메뉴 항목 (설명·번역·하이라이트·주석·AI에게 질문) */
export function menuItem(page: Page, name: string) {
  return page.getByRole("menu", { name: "고른 글로 할 일" }).getByRole("menuitem", { name, exact: true });
}

/** 고른 영역 곁의 도구줄 */
export function regionToolbar(page: Page) {
  return page.getByRole("toolbar", { name: "고른 영역으로 할 일" });
}

/** 메모 창에 쓰고 주석으로 저장한다 (선택 메뉴의 주석·영역 도구줄의 주석). */
export async function saveNote(page: Page, comment = "") {
  const memo = page.getByRole("form", { name: "주석 쓰기" });
  await memo.getByLabel("메모").fill(comment);
  await memo.getByRole("button", { name: "주석 저장" }).click();
  await expect(page.getByText("주석을 저장했습니다.")).toBeVisible();
}

/** 오른쪽 레일에서 패널을 연다 (이미 열려 있으면 그대로 둔다). */
export async function openPanel(page: Page, label: "Claude와 대화" | "선택 설명·질문" | "하이라이트" | "주석") {
  const button = page.getByRole("navigation", { name: "사이드바 패널" }).getByRole("button", { name: label, exact: true });
  if ((await button.getAttribute("aria-pressed")) !== "true") await button.click();
  await expect(button).toHaveAttribute("aria-pressed", "true");
}

/**
 * 저장된 quad를 다시 그린 표시와 같은 텍스트의 현재 위치 차이(CSS px, 네 변 중 최대).
 * layer는 현재 선택 표시(quad-overlay) 또는 저장된 주석 표시(annotation-overlay)다.
 */
export async function reprojectionError(
  page: Page,
  target: Target,
  rotation: number,
  zoom: number,
  layer: "quad-overlay" | "annotation-overlay" = "quad-overlay",
): Promise<number> {
  await showPage(page, target.pageIndex);
  const totalRotation = (EXPECTED.pages[target.pageIndex].rotation + rotation) % 360;
  const overlay = page.locator(`.page[data-page-number="${target.pageIndex + 1}"] > .${layer}`);
  // 표시가 이번 보기 기준으로 다시 그려진 뒤에만 잰다 (이전 보기끼리 비교하는 거짓 통과 방지).
  await expect(overlay).toHaveAttribute("data-rotation", String(totalRotation));
  await expect
    .poll(async () => Math.abs(Number(await overlay.getAttribute("data-scale")) - zoom * CSS_UNITS))
    .toBeLessThan(1e-9);

  let error = Infinity;
  await expect
    .poll(async () => {
      const { marks, lines } = await page.evaluate(({ pageIndex, texts, layer }) => {
        const pageDiv = document.querySelector(`.page[data-page-number="${pageIndex + 1}"]`)!;
        const box = (rect: DOMRect) => ({ left: rect.left, top: rect.top, right: rect.right, bottom: rect.bottom });
        const spans = [...pageDiv.querySelectorAll(".textLayer span")].filter((span) => texts.includes(span.textContent ?? ""));
        // 텍스트의 현재 위치: 글자 범위(Range)를 span 상자로 자른 영역. 글 진행 방향은 글자 범위가,
        // 수직 방향은 span(글꼴 크기 높이)이 정한다. 절대 크기는 expectMatchesTextSize가 따로 확인한다.
        const lines = spans.map((span) => {
          const range = document.createRange();
          range.selectNodeContents(span);
          const rects = [...range.getClientRects()].filter((rect) => rect.width > 0.5 && rect.height > 0.5);
          const host = span.getBoundingClientRect();
          return {
            left: Math.max(host.left, Math.min(...rects.map((rect) => rect.left))),
            top: Math.max(host.top, Math.min(...rects.map((rect) => rect.top))),
            right: Math.min(host.right, Math.max(...rects.map((rect) => rect.right))),
            bottom: Math.min(host.bottom, Math.max(...rects.map((rect) => rect.bottom))),
          };
        });
        const marks = [...pageDiv.querySelectorAll(`:scope > .${layer} > .quad-mark`)].map((mark) =>
          box(mark.getBoundingClientRect()),
        );
        return { marks, lines };
      }, { ...target, layer });
      error = marks.length === lines.length ? Math.max(...marks.map((mark, index) => edgeError(mark, lines[index]))) : Infinity;
      return error;
    })
    .toBeLessThanOrEqual(MAX_REPROJECTION_ERROR_PX);
  return error;
}

function edgeError(a: Rect, b: Rect): number {
  return Math.max(Math.abs(a.left - b.left), Math.abs(a.top - b.top), Math.abs(a.right - b.right), Math.abs(a.bottom - b.bottom));
}

/**
 * 이전 실행이 남긴 그 논문의 원문 위 대화(칩)를 지운다. E2E 데이터 폴더는 실행 사이에 남아, 지우지 않으면 칩이 쌓여
 * 고를 줄이나 그릴 영역을 덮는다(2026-10-03: context.spec이 남긴 칩이 regions R13의 2쪽 영역을 덮었다).
 */
export async function clearThreads(page: Page, paperId: string) {
  const { threads } = await (await page.request.get(`/api/v1/chat-threads?paper_id=${paperId}`)).json();
  for (const thread of threads as { session_id: string }[]) {
    expect((await page.request.delete(`/api/v1/chat-threads/${thread.session_id}`)).status()).toBe(204);
  }
}

/** 이전 실행이 남긴 주석을 지운다 (E2E 데이터 폴더는 실행 사이에 남는다). */
export async function clearAnnotations(page: Page, versionId: string) {
  for (const annotation of await listAnnotations(page, versionId)) {
    const response = await page.request.delete(`/api/v1/annotations/${annotation.annotation_id}`, {
      params: { revision: annotation.revision },
    });
    expect(response.status()).toBe(204);
  }
}

export async function listAnnotations(
  page: Page,
  versionId: string,
): Promise<{ annotation_id: string; revision: number }[]> {
  return (await (await page.request.get(`/api/v1/versions/${versionId}/annotations`)).json()).annotations;
}
