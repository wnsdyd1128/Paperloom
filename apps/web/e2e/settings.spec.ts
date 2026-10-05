/**
 * U6 설정 창과 답변 화면 (docs/UI_PLAN.md U6, 시안 Settings). 설정은 이 PC의 Core에 저장되고, 브리지가 차례마다 읽는다:
 * 기본 모델(--model), 답 언어와 개인화(--system-prompt-file 끝에 붙는다). 가짜 CLI 기록(fakeRuns)으로 확인한다.
 * 화면 설정은 테마(data-theme)·글꼴 크기(--reading-font-size)·복사할 때 수식 구분 기호다. 번역 창 글꼴은 번역 창 머리에서 바꾼다
 * (2026-10-04 사용자 요청으로 설정 화면에서 뺐다).
 * 설정은 E2E 데이터 폴더에 남아 다른 테스트에 번지므로 시작과 끝에 기본값으로 되돌린다.
 */
import { readFileSync } from "node:fs";

import { expect, type Locator, type Page, test } from "@playwright/test";

import { clearThreads, fakeRuns, FIXTURE_DIR, openPanel, showPage, startNewChat, uploadPdf } from "./fixture";

const CHAT = 'section[aria-labelledby="chat-heading"]';
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

async function resetSettings(page: Page) {
  expect((await page.request.put("/api/v1/settings", { data: DEFAULTS })).status()).toBe(200);
}

async function settings(page: Page) {
  return (await (await page.request.get("/api/v1/settings")).json()) as typeof DEFAULTS & { translation_font_size: number | null };
}

/** 논문을 Reader로 연다. 앞 실행이 남긴 원문 위 대화는 지운다(칩이 고를 줄을 덮지 않게). */
async function openReader(page: Page, file = "text-digital.pdf") {
  const { paperId, versionId } = await uploadPdf(page, readFileSync(new URL(file, FIXTURE_DIR)), file);
  await clearThreads(page, paperId);
  await page.goto(`/reader/${paperId}?version=${versionId}`);
  await expect(page.locator('.page[data-page-number="1"] .textLayer span').first()).toBeAttached();
  return { paperId, versionId };
}

/** 사이드바 대화의 새 대화로 묻고 답을 기다린다. */
async function askInSidebar(page: Page, question: string) {
  await openPanel(page, "Claude와 대화");
  const chat = page.locator(CHAT);
  await startNewChat(chat);
  await chat.getByRole("textbox", { name: "질문" }).fill(question);
  await chat.getByRole("textbox", { name: "질문" }).press("Enter");
  const turn = chat.locator(".chat-turn:not(.is-pending)").last();
  await expect(turn.locator(".chat-prompt")).toHaveText(question, { timeout: 15_000 });
  return turn;
}

/** 디자인 시스템의 라디오는 동그라미·칸만 보이고 input은 숨어 있어 이름표를 누른다. */
function radio(scope: Locator, name: string) {
  return scope.locator("label.radio, label.seg-opt", { hasText: name });
}

/** 한 줄을 골라 곁 메뉴를 띄운다. */
async function selectLine(page: Page, pageIndex: number, text: string) {
  await showPage(page, pageIndex);
  const span = page.locator(`.page[data-page-number="${pageIndex + 1}"] .textLayer span`, { hasText: text }).first();
  await span.scrollIntoViewIfNeeded();
  await span.evaluate((element) => {
    (document.activeElement as HTMLElement | null)?.blur(); // 질문 칸에 포커스가 있으면 단축키가 글자로 들어간다
    const range = document.createRange();
    range.selectNodeContents(element);
    document.getSelection()!.removeAllRanges();
    document.getSelection()!.addRange(range);
  });
  await expect(page.locator(".selection-menu")).toBeVisible();
}

function lastRun() {
  const run = fakeRuns().at(-1)!;
  return { model: run.args[run.args.indexOf("--model") + 1], system: run.system_prompt ?? "" };
}

test.beforeEach(async ({ page }) => resetSettings(page));
test.afterEach(async ({ page }) => resetSettings(page));

test("기본 설정·프롬프트 개인화를 저장하면 다음 차례부터 기본 모델·답 언어·개인화가 반영된다", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "dpr-1", "설정 흐름은 DPR과 무관하다");
  await page.goto("/");
  await page.getByRole("navigation", { name: "화면" }).getByRole("button", { name: "설정" }).click();
  const dialog = page.getByRole("dialog", { name: "설정" });
  await expect(dialog.getByRole("tab", { name: "기본 설정" })).toHaveAttribute("aria-selected", "true");
  await expect(dialog.getByRole("tab", { name: "기본 설정" })).toBeFocused();

  // 1) 기본 설정: 바꾸는 대로 저장한다
  await radio(dialog, "opus").click();
  await dialog.getByRole("combobox", { name: /답변 · 번역/ }).selectOption("en");
  await expect(radio(dialog, "120,000자")).toContainText("약 40쪽"); // 한 단 논문 쪽당 약 3,000자 어림
  await radio(dialog, "40,000자").click();
  await expect.poll(async () => (await settings(page)).default_model).toBe("opus");
  await expect.poll(async () => (await settings(page)).answer_language).toBe("en");
  await expect.poll(async () => (await settings(page)).paper_text_chars).toBe(40000);

  // 2) 프롬프트 개인화: 저장을 눌러야 저장한다. 바뀐 개수를 보이고, 기본값으로는 입력만 비운다
  await dialog.getByRole("tab", { name: "프롬프트 개인화" }).click();
  await dialog.getByRole("textbox", { name: /^시스템 프롬프트/ }).fill("E2E 개인화: 짧게 답하세요");
  await dialog.getByRole("textbox", { name: /^설명 프롬프트/ }).fill("E2E 설명 개인화: 비유를 써 주세요");
  await expect(dialog.getByText("바뀐 항목 2개")).toBeVisible();
  expect((await settings(page)).prompts.system).toBe("");
  await dialog.getByRole("button", { name: "저장" }).click();
  await expect(dialog.getByText("저장했습니다.")).toBeVisible();
  expect((await settings(page)).prompts).toEqual({ system: "E2E 개인화: 짧게 답하세요", explain: "E2E 설명 개인화: 비유를 써 주세요", translate: "", summary: "" });
  await page.keyboard.press("Escape");
  await expect(dialog).toHaveCount(0);

  // 3) 사이드바 대화: 기본 모델 이름, 논문 본문 한도, 시스템 프롬프트 끝의 답 언어·전체 개인화(설명 개인화는 아님)
  await openReader(page);
  await openPanel(page, "Claude와 대화");
  await expect(page.locator(CHAT).getByRole("combobox", { name: "모델" }).locator("option").first()).toHaveText("기본 모델 (Opus)");
  await expect(page.locator(CHAT).locator("label.chip-select").first()).toHaveAttribute("title", /40,000자/);
  await askInSidebar(page, `설정 반영 확인 ${Date.now()}`);
  let run = lastRun();
  expect(run.model).toBe("opus");
  expect(run.system).toContain("근거"); // 기본 규칙은 그대로 앞에 있다
  expect(run.system).toContain("- 답과 번역은 영어(English)로 쓰세요.");
  expect(run.system).toContain("  - 전체: E2E 개인화: 짧게 답하세요");
  expect(run.system).not.toContain("E2E 설명 개인화");
  expect(run.system).not.toContain("사용자가 쓴 언어로 답하세요");

  // 4) 원문 위 설명: 설명 개인화도 붙는다
  await selectLine(page, 1, "epsilonword");
  await page.keyboard.press("e");
  await expect(page.locator(".inline-layer .inline-window .inline-turn:not(.is-pending) .chat-answer").first()).toBeVisible({ timeout: 15_000 });
  run = lastRun();
  expect(run.system).toContain("  - 설명: E2E 설명 개인화: 비유를 써 주세요");

  // 5) Reader 머리의 설정 단추로도 연다. 바꾸면 대화창의 기본 모델 이름이 바로 바뀐다
  await page.locator(".inline-layer .inline-window").getByRole("button", { name: "접기" }).click();
  await page.getByRole("button", { name: "설정", exact: true }).click();
  await radio(page.getByRole("dialog", { name: "설정" }), "haiku").click();
  await page.keyboard.press("Escape");
  await expect(page.locator(CHAT).getByRole("combobox", { name: "모델" }).locator("option").first()).toHaveText("기본 모델 (Haiku)");
  await expect(page.getByRole("button", { name: "설정", exact: true })).toBeFocused(); // 연 단추로 돌아온다
});

test("화면 설정: 다크 모드(새로고침해도 남고 운영체제로 되돌린다), 글꼴 크기, 복사할 때 수식 구분 기호. 번역 창 글꼴은 번역 창 머리에서", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "dpr-1", "설정 흐름은 DPR과 무관하다");
  await page.context().grantPermissions(["clipboard-read", "clipboard-write"]);
  await page.emulateMedia({ colorScheme: "light" });
  await page.goto("/");
  const openDisplay = async () => {
    await page.getByRole("navigation", { name: "화면" }).getByRole("button", { name: "설정" }).click();
    await page.getByRole("dialog", { name: "설정" }).getByRole("tab", { name: "화면 설정" }).click();
    return page.getByRole("dialog", { name: "설정" });
  };
  let dialog = await openDisplay();
  const html = page.locator("html");

  // 1) 다크 모드
  const dark = dialog.getByRole("switch", { name: "다크 모드" });
  const background = () => page.evaluate(() => getComputedStyle(document.body).backgroundColor);
  const light = await background();
  await expect(dark).toHaveAttribute("aria-checked", "false");
  await dark.click();
  await expect(html).toHaveAttribute("data-theme", "dark");
  await expect(dark).toHaveAttribute("aria-checked", "true");
  await expect.poll(background).not.toBe(light);
  await expect.poll(async () => (await settings(page)).theme).toBe("dark"); // 저장이 끝난 뒤 새로고침한다
  await page.reload();
  await expect(html).toHaveAttribute("data-theme", "dark");
  dialog = await openDisplay();
  await dialog.getByRole("button", { name: "운영체제 설정 따르기" }).click();
  await expect(html).not.toHaveAttribute("data-theme", /.*/);
  await expect(dialog.getByRole("switch", { name: "다크 모드" })).toHaveAttribute("aria-checked", "false");

  // 2) 글꼴 크기: 설명·대화·번역 창의 글자 크기
  await dialog.getByLabel("글꼴 크기").fill("18");
  await expect.poll(() => page.evaluate(() => document.documentElement.style.getPropertyValue("--reading-font-size"))).toBe("18px");
  await expect.poll(async () => (await settings(page)).font_size).toBe(18);

  // 3) 번역 창 글꼴은 설정 화면에 없다(2026-10-04 사용자 요청)
  await expect(dialog.getByRole("switch", { name: "번역 창 글꼴 따로 정하기" })).toHaveCount(0);

  // 4) 수식 구분 기호: bracket
  await radio(dialog, "bracket").click();
  await expect.poll(async () => (await settings(page)).math_delimiters).toBe("bracket");
  await page.keyboard.press("Escape");

  // 답 복사: 가짜 답의 $C_i \le T_i$가 \(C_i \le T_i\)로
  await openReader(page);
  const turn = await askInSidebar(page, `수식 복사 확인 ${Date.now()}`);
  await expect(turn.locator(".chat-answer")).toHaveCSS("font-size", "18px");
  await turn.getByRole("button", { name: "복사", exact: true }).click();
  await expect.poll(() => page.evaluate(() => navigator.clipboard.readText())).toContain("\\(C_i \\le T_i\\)");
  expect(await page.evaluate(() => navigator.clipboard.readText())).not.toContain("$C_i");

  // 번역 창: 처음에는 글꼴 크기(18), 머리의 A−/A+로 바꾸면 저장한다(설정 화면에 없어도 늘 보인다). 복사도 수식 구분 기호를 따른다
  await selectLine(page, 1, "epsilonword");
  await page.keyboard.press("t");
  const translation = page.locator('.inline-layer .inline-window[data-kind="translate"]');
  await expect(translation.locator(".inline-turn:not(.is-pending) .chat-answer").first()).toBeVisible({ timeout: 15_000 });
  await expect(translation.locator(".chat-answer").first()).toHaveCSS("font-size", "18px");
  await expect(translation.locator(".inline-font-value")).toHaveText("18");
  await translation.getByRole("button", { name: "번역 글꼴 크게" }).click();
  await expect(translation.locator(".inline-font-value")).toHaveText("19");
  await expect(translation.locator(".chat-answer").first()).toHaveCSS("font-size", "19px");
  await expect.poll(async () => (await settings(page)).translation_font_size).toBe(19);
  await expect(turn.locator(".chat-answer")).toHaveCSS("font-size", "18px"); // 사이드바는 그대로
  await translation.getByRole("button", { name: "번역 복사" }).click();
  await expect.poll(() => page.evaluate(() => navigator.clipboard.readText())).toContain("\\(C_i \\le T_i\\)");
});

/**
 * 2026-10-03 사용자 확인: 운영체제는 어두운데 설정을 밝은 판으로 두면 스크롤 막대가 어두웠다. Reader가 불러오는 PDF.js
 * pdf_viewer.css의 `:root { color-scheme: light dark }`가 뒤에 와서 우리 `:root { color-scheme: light }`를 덮었다.
 * 스크롤 막대는 운영체제가 그려 스크린샷 비교 대신 문서 뿌리의 color-scheme을 본다.
 */
test("설정한 테마가 운영체제와 달라도 스크롤 막대 색(color-scheme)은 설정을 따른다 (Reader를 연 뒤에도)", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "dpr-1", "테마는 DPR과 무관하다");
  const scheme = () => page.evaluate(() => getComputedStyle(document.documentElement).colorScheme);
  for (const [system, theme] of [["dark", "light"], ["light", "dark"]] as const) {
    await page.emulateMedia({ colorScheme: system });
    expect((await page.request.put("/api/v1/settings", { data: { ...DEFAULTS, theme } })).status()).toBe(200);
    await openReader(page);
    await expect(page.locator("html")).toHaveAttribute("data-theme", theme);
    await expect.poll(scheme).toBe(theme);
    await page.getByRole("button", { name: "서재로 돌아가기" }).click();
    await expect.poll(scheme).toBe(theme);
  }
});

test("답변 화면: 모든 논문의 대화를 최근 순으로 보이고, 누르면 그 논문의 사이드바 대화나 원문 위 창을 연다", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "dpr-1", "대화 흐름은 DPR과 무관하다");
  const { paperId } = await openReader(page);
  const question = `답변 화면 대화 ${Date.now()}`;
  await askInSidebar(page, question);
  await selectLine(page, 1, "epsilonword");
  await page.keyboard.press("e");
  const inline = page.locator(".inline-layer .inline-window");
  await expect(inline.locator(".inline-turn:not(.is-pending) .chat-answer").first()).toBeVisible({ timeout: 15_000 });
  // 원문 위 대화 기록은 첫 답 뒤에 남는다
  let explain: { session_id: string; anchor_id: string } | undefined;
  await expect
    .poll(async () => {
      const { conversations } = await (await page.request.get("/api/v1/conversations")).json();
      explain = conversations[0]?.kind === "explain" && conversations[0].paper_id === paperId ? conversations[0] : undefined;
      return explain !== undefined;
    })
    .toBe(true);
  await inline.getByRole("button", { name: "접기" }).click();

  // 서재 → 답변
  await page.getByRole("button", { name: "서재로 돌아가기" }).click();
  await page.getByRole("navigation", { name: "화면" }).getByRole("button", { name: "답변" }).click();
  await expect(page).toHaveURL(/\/answers$/);
  await page.reload(); // 서버가 /answers에도 웹앱을 돌려준다
  await expect(page.getByRole("navigation", { name: "화면" }).getByRole("button", { name: "답변" })).toHaveAttribute("aria-current", "page");
  const rows = page.locator(".conversation-list li");
  await expect(rows.first()).toHaveAttribute("data-session-id", explain!.session_id);
  await expect(rows.first().locator(".tag")).toHaveText("설명");
  await expect(rows.first()).toContainText("Paperloom text fixture digital (synthetic) · p.2");
  const chatRow = rows.filter({ hasText: question });
  await expect(chatRow.locator(".tag")).toHaveText("대화");
  await expect(chatRow.locator(".conversation-count")).toHaveText("답변 1");
  await expect(page.getByRole("heading", { name: "Claude Desktop에서 저장한 답변" })).toBeVisible();

  // 1) 사이드바 대화: 그 대화를 사이드바에서 연다
  await chatRow.getByRole("button").click();
  await expect(page).toHaveURL(new RegExp(`/reader/${paperId}\\?version=[^&]+&session=`));
  await expect(page.getByRole("navigation", { name: "사이드바 패널" }).getByRole("button", { name: "Claude와 대화", exact: true })).toHaveAttribute("aria-pressed", "true");
  await expect(page.locator(CHAT).locator(".chat-turn .chat-prompt").last()).toHaveText(question);

  // 2) 원문 위 대화: 그 위치를 열고 그 자리 창을 펼친다
  await page.goBack();
  await expect(page).toHaveURL(/\/answers$/);
  await rows.first().getByRole("button").click();
  await expect(page).toHaveURL(new RegExp(`anchor=${explain!.anchor_id}.*session=${explain!.session_id}`));
  await expect(inline).toHaveAttribute("data-kind", "explain");
  await expect(inline.locator(".chat-answer").first()).toContainText("가짜 답");
});
