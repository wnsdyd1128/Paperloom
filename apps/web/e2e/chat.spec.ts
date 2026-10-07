/**
 * ADR 0003 · docs/UI_PLAN.md U2: Reader에서 Claude와 대화한다. 글·그림을 고르면 곁에 메뉴가 뜨고, 설명·번역·질문은
 * 고른 자리 위의 창에서 답한다. 창은 접으면 칩이 되고, 새로고침 뒤에도 남고, 사이드바 대화로 옮길 수 있다.
 * 사이드바 "Claude와 대화"는 논문마다 이어지고, 답은 Markdown(수식 포함)으로 그려진다.
 * 브리지(8794)는 실제 Claude Code 대신 가짜 CLI(tests/fixtures/fake_claude)를 실행한다(playwright.config.ts).
 * 실제 Claude Code 확인은 G4 K10 기록에 있다.
 */
import { readFileSync } from "node:fs";

import { expect, type Locator, type Page, test } from "@playwright/test";

import {
  clearAnnotations,
  clearThreads,
  fakeRuns,
  type FakeRun,
  FIXTURE_DIR,
  menuItem,
  openPanel,
  regionToolbar,
  saveNote,
  SELECTION_STATUS,
  showPage,
  startNewChat,
  uploadPdf,
} from "./fixture";

const CHAT = 'section[aria-labelledby="chat-heading"]';
const MENU = ".selection-menu";
const EXPLAIN_QUESTION = "고른 부분을 쉽게 설명해 주세요. 필요한 정의와 전제도 함께 알려 주세요.";

function resumed(run: FakeRun): string | null {
  return run.args.includes("--resume") ? run.args[run.args.indexOf("--resume") + 1] : null;
}

/**
 * 새 논문으로 Reader를 연다. 같은 fixture가 이미 있으면(앞 실행) 그 논문의 대화도 남아 있으므로, 원문 위 대화(칩)는
 * 지우고 시작한다(칩이 쌓이면 고른 줄을 덮는다). 사이드바 대화는 남는다.
 */
async function openPaper(page: Page, file: string) {
  const { paperId, versionId } = await uploadPdf(page, readFileSync(new URL(file, FIXTURE_DIR)), file);
  await clearThreads(page, paperId);
  await page.goto(`/reader/${paperId}?version=${versionId}`);
  await expect(page.locator('.page[data-page-number="1"] .textLayer span').first()).toBeAttached();
  return { paperId, versionId };
}

/** 마우스로 글 한 줄을 끌어 고른다. 손을 떼면 메뉴가 뜬다. */
async function dragLine(page: Page, pageIndex: number, text: string) {
  await showPage(page, pageIndex);
  const span = page.locator(`.page[data-page-number="${pageIndex + 1}"] .textLayer span`, { hasText: text }).first();
  await span.scrollIntoViewIfNeeded();
  const box = (await span.boundingBox())!;
  await page.mouse.move(box.x + 1, box.y + box.height / 2);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width - 1, box.y + box.height / 2, { steps: 6 });
  await expect(page.locator(MENU)).toHaveCount(0); // 끄는 동안에는 띄우지 않는다
  await page.mouse.up();
  await expect(page.locator(MENU)).toBeVisible();
}

/** 원문 위에 펼친 창 (한 번에 하나) */
function openWindow(page: Page) {
  return page.locator(".inline-layer .inline-window");
}

test("글을 고르면 곁에 메뉴가 뜨고, 설명은 원문 위 창에서 답하고, 접고 다시 펴고, 사이드바 대화로 옮긴다", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "dpr-1", "대화 흐름은 DPR과 무관하다");
  await openPaper(page, "text-digital.pdf");
  await dragLine(page, 1, "epsilonword");
  const box = (await page.locator(MENU).boundingBox())!;
  const line = (await page.locator('.page[data-page-number="2"] .textLayer span', { hasText: "epsilonword" }).first().boundingBox())!;
  expect(box.y).toBeGreaterThanOrEqual(line.y + line.height - 1); // 고른 줄 바로 아래
  await expect(page.locator(`${MENU} .selection-menu-label`)).toHaveText(["설명", "번역", "하이라이트", "주석", "AI에게 질문"]);

  // Esc로 닫고, 빈 곳을 눌러 선택을 푼 뒤 다시 고르면 또 뜬다
  await page.keyboard.press("Escape");
  await expect(page.locator(MENU)).toHaveCount(0);
  await page.evaluate(() => document.getSelection()!.removeAllRanges());
  await dragLine(page, 1, "epsilonword");

  // 1) 설명: 단축키 E로 바로 묻고, 고른 자리 아래 창에서 답한다
  const runsBefore = fakeRuns().length;
  await page.keyboard.press("e");
  const thread = openWindow(page);
  await expect(thread).toHaveAttribute("data-kind", "explain");
  await expect(thread.locator(".chat-answer strong").first()).toHaveText("가짜 답", { timeout: 15_000 });
  await expect(thread.locator(".chat-answer .katex")).toHaveCount(2); // 수식 $C_i \le T_i$와 $S = A_i \tag{1.4}$를 그렸다
  await expect(thread.locator(".chat-answer .katex-error")).toHaveCount(0); // 문장 안 식 번호도 빨간 오류가 아니다
  await expect(thread.locator(".chat-answer .katex").nth(1)).toContainText("(1.4)");
  await expect(thread.locator(".chat-answer")).not.toContainText("**");
  await expect(thread.locator(".inline-question")).toHaveCount(0); // 메뉴가 정한 첫 질문은 보이지 않는다
  await expect(page.locator(MENU)).toHaveCount(0);
  const windowBox = (await thread.boundingBox())!;
  expect(windowBox.y).toBeGreaterThanOrEqual(line.y + line.height - 1); // 고른 줄 아래
  // 보낸 근거: 접어 두면 종류와 쪽만, 펼치면 근거마다 글이 보인다
  await expect(thread.locator(".evidence-toggle")).toContainText("선택한 글");
  await thread.locator(".evidence-toggle").click();
  await expect(thread.locator('li[data-role="selected_text"] .evidence-text')).toContainText("epsilonword paragraph that a reader");
  await thread.locator(".evidence-toggle").click();
  // 창 안의 글을 골라도(창이 쪽 위에 겹쳐 있어도) PDF 선택이 아니다: 메뉴가 뜨지 않고 선택 상태도 비어 있다
  await thread.locator(".chat-answer p").first().evaluate((element) => {
    const range = document.createRange();
    range.selectNodeContents(element);
    document.getSelection()!.removeAllRanges();
    document.getSelection()!.addRange(range);
  });
  await page.waitForTimeout(300);
  await expect(page.locator(SELECTION_STATUS)).toHaveText("");
  await expect(page.locator(MENU)).toHaveCount(0);
  await page.evaluate(() => document.getSelection()!.removeAllRanges());
  const [firstRun] = fakeRuns().slice(runsBefore);
  expect(firstRun.args).toContain("--safe-mode");
  expect(firstRun.env).toEqual([]);
  expect(resumed(firstRun)).toBeNull(); // 고른 곳마다 새 대화
  expect(firstRun.message.message.content.at(-1)!.text).toContain("> epsilonword paragraph that a reader");
  expect(firstRun.message.message.content.at(-1)!.text).toContain(EXPLAIN_QUESTION);
  // 앞쪽부터 고른 쪽(2쪽) 다음 쪽까지와 참고문헌 쪽(이 문서는 없음)을 함께 보낸다 (2026-10-04 사용자 요청: 18쪽이면 1–18쪽 + 19쪽)
  expect(firstRun.message.message.content.at(-1)!.text).toContain("- 범위: 논문 본문 앞쪽부터 3쪽까지 (");
  // 보낸 근거 줄은 실제로 보낸 쪽을 그대로 적는다(처음–끝만 적으면 전문을 보낸 것처럼 보였다)
  await expect(thread.locator(".evidence-toggle")).toContainText("논문 본문 (p.1–3)");

  // 2) 근거 표시를 누르면 원문 위치를 연다. 논문의 참고문헌 번호 [12]는 글자 그대로다(근거와 헷갈리지 않게)
  await expect(thread.locator(".chat-answer").first()).toContainText("참고문헌 [12]는 근거가 아닙니다");
  await expect(thread.locator(".chat-answer .cite-chip")).toHaveText(["근거 1"]);
  await thread.getByRole("button", { name: "근거 1", exact: true }).first().click();
  await expect(page).toHaveURL(/anchor=/);

  // 3) 창에서 이어 묻기: Enter로 보낸다. 같은 대화(--resume)에 질문만. 질문·답의 HTML은 글자로만, Markdown 이미지는 불러오지 않는다
  const followUp = '더 쉽게 ![추적](http://127.0.0.1:9/t.png) <img src=x onerror="window.__chatInjected = true">';
  const input = thread.getByRole("textbox", { name: "이어서 물어보기" });
  await input.fill(followUp);
  // 한글 조합 중의 Enter는 글자를 마무리하는 것이므로 보내지 않는다
  await input.evaluate((element) =>
    element.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", isComposing: true, bubbles: true, cancelable: true })),
  );
  await expect(input).toHaveValue(followUp);
  await input.press("Enter");
  await expect(thread.locator(".inline-question")).toHaveText(followUp, { timeout: 15_000 });
  await expect(thread.locator(".inline-turn:not(.is-pending)").last().locator(".chat-answer")).toContainText(
    "[그림: 추적] <img src=x onerror=", // 가짜 CLI는 질문을 60자까지 되돌려 준다
    { timeout: 15_000 },
  );
  await expect(thread.locator(".inline-window-body img")).toHaveCount(0);
  expect(await page.evaluate(() => (window as unknown as { __chatInjected?: boolean }).__chatInjected)).toBeUndefined();
  const secondRun = fakeRuns().at(-1)!;
  const session = resumed(secondRun);
  expect(session).toMatch(/^[0-9a-f-]{36}$/);
  expect(secondRun.message.message.content).toEqual([{ type: "text", text: followUp }]);

  // 4) 접으면 원문 위 제목 칩이 되고, 누르면 다시 펼친다
  const title = (await thread.locator(".inline-window-title").textContent())!;
  const key = (await thread.getAttribute("data-thread-key"))!; // 첫 답 전에 연 창은 화면 안의 임시 이름이다
  await thread.getByRole("button", { name: "접기" }).click();
  await expect(openWindow(page)).toHaveCount(0);
  const chip = page.locator(`.thread-chip[data-thread-key="${key}"]`);
  await expect(chip).toContainText(title);
  await expect(chip).toContainText("답변 2");
  // 칩이 고른 줄(오른쪽 단) 위에 겹쳐 있어도, 본문에서 끌기 시작하면 칩 아래 글을 고를 수 있다
  const chipBox = (await chip.boundingBox())!;
  const lineBox = (await page.locator('.page[data-page-number="2"] .textLayer span', { hasText: "epsilonword" }).first().boundingBox())!;
  expect(chipBox.x < lineBox.x + lineBox.width && lineBox.x < chipBox.x + chipBox.width, "칩이 그 줄과 가로로 겹친다").toBe(true);
  expect(chipBox.y < lineBox.y + lineBox.height && lineBox.y < chipBox.y + chipBox.height, "칩이 그 줄과 세로로 겹친다").toBe(true);
  await dragLine(page, 1, "epsilonword");
  await expect(page.locator(SELECTION_STATUS)).toHaveText("2쪽에서 1줄을 골랐습니다: epsilonword paragraph that a reader");
  await page.keyboard.press("Escape");
  await page.evaluate(() => document.getSelection()!.removeAllRanges());
  await chip.click();
  await expect(openWindow(page).locator(".inline-question")).toHaveText(followUp);

  // 5) 새로고침해도 칩으로 남고(이제 대화 ID로 불린다), 사이드바 "선택 설명·질문"에서 열 수 있다
  await page.reload();
  const savedChip = page.locator(`.thread-chip[data-thread-key="${session}"]`);
  await expect(savedChip).toContainText(title);
  await openPanel(page, "선택 설명·질문");
  const row = page.locator(`.thread-row[data-thread-key="${session}"]`);
  await expect(row).toContainText(title);
  await expect(row).toContainText("답변 2");
  await row.click();
  await expect(openWindow(page).locator(".inline-question")).toHaveText(followUp);
  await expect(openWindow(page).locator(".evidence-toggle")).toContainText("선택한 글"); // 첫 packet을 다시 받았다

  // 6) 사이드바로 옮기면 사이드바 대화에서 이어 간다. 원문 위 칩은 사라진다
  await openWindow(page).getByRole("button", { name: "사이드바로 옮기기" }).click();
  const chat = page.locator(CHAT);
  await expect(page.getByRole("button", { name: "Claude와 대화", exact: true })).toHaveAttribute("aria-pressed", "true");
  await expect(chat.locator(".chat-turn").last().locator(".chat-prompt")).toHaveText(followUp);
  await expect(savedChip).toHaveCount(0);
  const chatInput = chat.getByRole("textbox", { name: "질문" });
  await chatInput.fill("사이드바에서 이어서");
  await chat.getByLabel("모델").selectOption("haiku");
  await chatInput.press("Enter");
  await expect(chat.locator(".chat-turn:not(.is-pending)").last().locator(".chat-prompt")).toHaveText("사이드바에서 이어서", { timeout: 15_000 });
  const thirdRun = fakeRuns().at(-1)!;
  expect(resumed(thirdRun)).toBe(session);
  expect(thirdRun.args[thirdRun.args.indexOf("--model") + 1]).toBe("haiku");

  // 7) 새 대화를 시작했다가, 대화 기록에서 앞 대화로 돌아간다. 옮겨 온 대화는 첫 질문이 아니라 그 대화의 제목으로 보인다
  await chat.getByRole("button", { name: "새 대화", exact: true }).click();
  await expect(chat.locator(".chat-turn")).toHaveCount(0);
  await expect(chat.locator(".chat-guide")).toBeVisible();
  await chat.getByRole("button", { name: "대화 기록", exact: true }).click();
  const moved = chat.locator(`.chat-history-item[data-session-id="${session}"]`);
  await expect(moved).toContainText(title);
  await moved.locator("button").first().click();
  await expect(chat.locator(".chat-turn").last().locator(".chat-prompt")).toHaveText("사이드바에서 이어서");
  await expect(chat.locator(".chat-title")).toHaveText(title);
});

test("원문 위 대화는 사이드바 대화 기록에 없고, 원문 위 창에서 지워도 그 기록에 나타나지 않는다", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "dpr-1", "대화 흐름은 DPR과 무관하다");
  const { paperId } = await openPaper(page, "text-digital.pdf");
  await dragLine(page, 1, "epsilonword");
  await page.keyboard.press("e");
  await expect(openWindow(page).locator(".chat-answer strong").first()).toHaveText("가짜 답", { timeout: 15_000 });
  let session = "";
  await expect
    .poll(async () => {
      const { threads } = await (await page.request.get(`/api/v1/chat-threads?paper_id=${paperId}`)).json();
      session = threads[0]?.session_id ?? "";
      return session;
    })
    .not.toBe("");

  // 새로고침하면 사이드바 대화는 이 논문의 답을 모두 읽는다. 원문 위 대화는 그 기록에 없다
  await page.reload();
  const chat = page.locator(CHAT);
  const openHistory = async () => {
    await openPanel(page, "Claude와 대화");
    const toggle = chat.getByRole("button", { name: "대화 기록", exact: true });
    if ((await toggle.getAttribute("aria-expanded")) !== "true") await toggle.click();
  };
  await openHistory();
  await expect(chat.locator(".chat-history")).toBeVisible();
  await expect(chat.locator(`.chat-history-item[data-session-id="${session}"]`)).toHaveCount(0);

  // 원문 위 창에서 지우면(답도 버린다) 사이드바 대화 기록에 나타나지 않는다 (2026-10-03 사용자 확인: 나타나고 지우기는 실패했다)
  const chip = page.locator(`.thread-chip[data-thread-key="${session}"]`);
  await chip.click();
  page.once("dialog", (dialog) => void dialog.accept());
  await openWindow(page).getByRole("button", { name: "삭제" }).click();
  await expect(chip).toHaveCount(0);
  await openHistory();
  await expect(chat.locator(".chat-history")).toBeVisible();
  await expect(chat.locator(`.chat-history-item[data-session-id="${session}"]`)).toHaveCount(0);
});

test("원문 위 창은 머리를 끌어 옮기고(글은 고르지 않는다), 접었다 펴면 고른 자리 아래로 돌아온다", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "dpr-1", "대화 흐름은 DPR과 무관하다");
  await openPaper(page, "text-digital.pdf");
  await dragLine(page, 1, "epsilonword");
  const runsBefore = fakeRuns().length;
  await menuItem(page, "번역").click();
  const thread = openWindow(page);
  await expect(thread).toHaveAttribute("data-kind", "translate");
  await expect(thread.locator(".chat-answer strong").first()).toHaveText("가짜 답", { timeout: 15_000 });
  await page.evaluate(() => document.getSelection()!.removeAllRanges());
  // 번역은 논문 본문 없이 고른 글과 앞뒤 문단만 보낸다(사용량, 2026-10-02 사용자 결정)
  expect(fakeRuns().slice(runsBefore)[0].message.message.content.at(-1)!.text).not.toMatch(/### \[근거 \d+\] 논문 본문/);
  // 스크롤 내용 좌표: 칩을 누르거나 창이 스크롤 폭을 넓히면 화면이 밀릴 수 있다
  const inContent = (locator: Locator) =>
    locator.evaluate((element) => {
      const scroll = element.closest(".reader-scroll")!;
      const box = element.getBoundingClientRect();
      const frame = scroll.getBoundingClientRect();
      return { x: box.left - frame.left - scroll.clientLeft + scroll.scrollLeft, y: box.top - frame.top - scroll.clientTop + scroll.scrollTop };
    });
  const home = await inContent(thread);
  const dragHead = async (dx: number, dy: number) => {
    await thread.locator(".inline-window-title").scrollIntoViewIfNeeded(); // 오른쪽 끝으로 옮긴 머리는 가로 스크롤 밖에 있을 수 있다
    const title = (await thread.locator(".inline-window-title").boundingBox())!;
    await page.mouse.move(title.x + 10, title.y + title.height / 2);
    await page.mouse.down();
    await page.mouse.move(title.x + 10 + dx, title.y + title.height / 2 + dy, { steps: 8 });
    await page.mouse.up();
  };

  // 1) 머리를 끈 만큼 옮긴다. 두 번 끌면 이어서 옮긴다. 끄는 동안 PDF 글을 고르지 않는다
  await dragHead(60, -40);
  await dragHead(30, 0);
  const moved = await inContent(thread);
  expect(moved.x - home.x).toBeCloseTo(90, 0);
  expect(moved.y - home.y).toBeCloseTo(-40, 0);
  expect(await page.evaluate(() => document.getSelection()!.isCollapsed)).toBe(true);
  await expect(page.locator(SELECTION_STATUS)).toHaveText("");
  await expect(page.locator(MENU)).toHaveCount(0);

  // 2) 왼쪽 밖으로 끌어도 스크롤 내용의 왼쪽 끝에서, 오른쪽 밖으로 끌어도 머리가 쪽들의 폭 안에 120px 남게 멈춘다
  await dragHead(-5000, 0);
  expect((await inContent(thread)).x).toBeCloseTo(0, 0);
  expect(await page.evaluate(() => document.getSelection()!.isCollapsed)).toBe(true); // 포인터가 창 밖으로 벗어나도
  await dragHead(5000, 0);
  await dragHead(5000, 0); // 앞 끌기로 스크롤 폭이 넓어져도 더 나가지 않는다
  const viewerWidth = await page.locator(".pdfViewer").evaluate((element) => (element as HTMLElement).offsetLeft + element.scrollWidth);
  expect((await inContent(thread)).x).toBeCloseTo(viewerWidth - 120, 0);

  // 3) 머리의 버튼은 끌기가 아니라 누름이다. 접었다 펴면 고른 자리 아래로 돌아온다
  const key = (await thread.getAttribute("data-thread-key"))!;
  await thread.getByRole("button", { name: "접기" }).click();
  await expect(openWindow(page)).toHaveCount(0);
  await page.locator(`.thread-chip[data-thread-key="${key}"]`).click();
  const back = await inContent(openWindow(page));
  expect(back.x).toBeCloseTo(home.x, 0);
  expect(back.y).toBeCloseTo(home.y, 0);
});

test("그림을 누르면 영역 도구줄이 뜨고, AI에게 질문은 원문 위 창에서 묻거나 사이드바 대화로 옮겨 그림과 함께 묻는다", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "dpr-1", "대화 흐름은 DPR과 무관하다");
  await openPaper(page, "figures.pdf");
  await showPage(page, 0);
  const figures = JSON.parse(readFileSync(new URL("figures.json", FIXTURE_DIR), "utf-8")).figures;
  const [u0, v0, u1, v1] = figures.find((figure: { name: string }) => figure.name === "vector").normalized;
  const clickFigure = async () => {
    const frame = (await page.locator('.page[data-page-number="1"]').boundingBox())!;
    // 쪽의 그림 후보를 받기 전에 누르면 아무 일도 없다(figures.ts). 도구줄이 뜰 때까지 다시 누른다
    await expect(async () => {
      await page.mouse.click(frame.x + (frame.width * (u0 + u1)) / 2, frame.y + (frame.height * (v0 + v1)) / 2);
      await expect(regionToolbar(page)).toBeVisible({ timeout: 1_000 });
    }).toPass({ timeout: 15_000 });
  };
  await clickFigure();
  const toolbar = regionToolbar(page);
  await expect(toolbar.getByRole("radio")).toHaveCount(3);
  await expect(toolbar.getByRole("radio", { name: "그림" })).toBeChecked();
  await expect(toolbar.getByRole("button")).toHaveText([/설명/, "AI에게 질문", "주석", /그림 복사/]);

  // 1) 원문 위 질문 창: 쓰고 Enter로 보내면 같은 자리에서 답한다
  await toolbar.getByRole("button", { name: "AI에게 질문" }).click();
  const ask = page.getByRole("form", { name: "AI에게 질문" });
  await expect(ask).toContainText("선택한 글과 앞뒤 문단을 함께 보냅니다");
  let runsBefore = fakeRuns().length;
  await ask.getByRole("textbox", { name: "질문" }).fill("이 그림은 무엇을 비교하나요?");
  await ask.getByRole("textbox", { name: "질문" }).press("Enter");
  const thread = openWindow(page);
  await expect(thread).toHaveAttribute("data-kind", "ask");
  await expect(thread.locator(".inline-question")).toHaveText("이 그림은 무엇을 비교하나요?");
  await expect(thread.locator(".chat-answer")).toContainText("이미지 1개를 받았습니다", { timeout: 15_000 });
  let run = fakeRuns().slice(runsBefore)[0];
  expect(resumed(run)).toBeNull();
  expect(run.message.message.content.map((block) => block.type)).toEqual(["image", "text"]);
  await thread.getByRole("button", { name: "접기" }).click();

  // 2) 질문 창을 사이드바 대화로 옮기면 고른 그림이 입력칸에 붙고, 쓰던 질문도 따라간다
  await clickFigure();
  await regionToolbar(page).getByRole("button", { name: "AI에게 질문" }).click();
  await page.getByRole("form", { name: "AI에게 질문" }).getByRole("textbox", { name: "질문" }).fill("이 그림의 캡션은 뭐라고 하나요?");
  await page.getByRole("button", { name: "사이드바 대화로 옮기기" }).click();
  const chat = page.locator(CHAT);
  await expect(chat.locator(".chat-attachments li")).toContainText(["그림 · p.1"]);
  await expect(chat.getByRole("textbox", { name: "질문" })).toHaveValue("이 그림의 캡션은 뭐라고 하나요?");
  await startNewChat(chat); // 앞 실행의 대화가 있으면 새로 시작한다
  runsBefore = fakeRuns().length;
  await chat.getByRole("button", { name: "보내기" }).click();
  const turn = chat.locator(".chat-turn:not(.is-pending)").last();
  await expect(turn.locator(".chat-answer")).toContainText("이미지 1개를 받았습니다", { timeout: 15_000 });
  await expect(turn.locator(".chat-quote img")).toBeVisible(); // 고른 그림이 인용으로 보인다
  await expect(chat.locator(".chat-attachments")).toHaveCount(0);
  run = fakeRuns().slice(runsBefore)[0];
  expect(resumed(run)).toBeNull(); // 새 대화
  expect(run.message.message.content.map((block) => block.type)).toEqual(["image", "text"]);
  expect(run.message.message.content[1].text).toContain("Figure 1. Synthetic bar chart with three bars.");
  expect(run.message.message.content[1].text).toContain("## 질문 (질문)\n\n이 그림의 캡션은 뭐라고 하나요?");
});

test("대화 범위: 논문 본문은 대화에 한 번만, 현재 쪽은 그 쪽만 보낸다(선택만은 없다)", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "dpr-1", "대화 흐름은 DPR과 무관하다");
  await openPaper(page, "text-digital.pdf");
  await openPanel(page, "Claude와 대화");
  const chat = page.locator(CHAT);
  await startNewChat(chat);
  const scope = chat.getByLabel("범위");
  await expect(scope).toHaveValue("paper"); // 기본은 논문 본문 (시안 3a·D2)
  const input = chat.getByRole("textbox", { name: "질문" });
  const lastTurn = () => chat.locator(".chat-turn:not(.is-pending)").last();
  const askAndWait = async (question: string) => {
    const before = fakeRuns().length;
    await input.fill(question);
    await input.press("Enter");
    await expect(lastTurn().locator(".chat-prompt")).toHaveText(question, { timeout: 15_000 });
    await expect(lastTurn().locator(".chat-answer strong").first()).toHaveText("가짜 답");
    const runs = fakeRuns().slice(before);
    expect(runs).toHaveLength(1);
    return runs[0];
  };

  // 1) 논문 본문: 앞쪽부터 쪽마다 근거, 기본 한도 120,000자
  const first = await askAndWait("이 논문은 무엇을 다루나요?");
  expect(resumed(first)).toBeNull();
  const paperText = first.message.message.content.at(-1)!.text!;
  expect(paperText).toContain("### [근거 1] 논문 본문 · ");
  expect(paperText).toContain("Paperloom Extraction Sample"); // 첫 쪽 맨 위의 제목도 들어간다
  expect(paperText).toContain("- 범위: 논문 본문");
  expect(paperText).toMatch(/본문 [\d,]+\/120,000자/);
  await expect(lastTurn().locator(".chat-quote")).toHaveCount(0); // 고른 부분이 없다
  await lastTurn().getByRole("button", { name: "근거 1", exact: true }).click(); // 본문 근거 번호도 원문 위치(쪽·문단)로 간다
  await expect(page).toHaveURL(/page=1&block=/);

  // 2) 같은 대화에서 다시 물으면 본문을 다시 보내지 않는다(질문만)
  const second = await askAndWait("결론은 무엇인가요?");
  const session = resumed(second);
  expect(session).toMatch(/^[0-9a-f-]{36}$/);
  expect(second.message.message.content).toEqual([{ type: "text", text: "결론은 무엇인가요?" }]);

  // 3) 현재 쪽: 3쪽으로 옮겨 물으면 그 쪽 본문만 새로 보낸다(같은 대화). 그 쪽에서 다시 물으면 질문만
  await page.getByLabel("쪽 번호").fill("3");
  await page.getByLabel("쪽 번호").press("Enter");
  await expect(page.getByLabel("쪽 번호")).toHaveValue("3");
  await scope.selectOption("page");
  const onPage = await askAndWait("이 쪽은 무엇을 말하나요?");
  expect(resumed(onPage)).toBe(session);
  const pageText = onPage.message.message.content.at(-1)!.text!;
  expect(pageText).toContain("- 범위: 3쪽 본문");
  expect(pageText.match(/^### \[근거 \d+\] .+$/gm)).toEqual([expect.stringMatching(/^### \[근거 1\] 논문 본문 · .+ · 3쪽$/)]);
  const again = await askAndWait("한 문장으로 줄이면?");
  expect(again.message.message.content).toEqual([{ type: "text", text: "한 문장으로 줄이면?" }]);

  // 4) 범위는 논문 본문·현재 쪽뿐이다(2026-10-04 사용자 요청으로 "선택만"을 뺐다. 고른 위치는 첨부로 붙인다)
  await chat.getByRole("button", { name: "새 대화", exact: true }).click();
  await expect(scope.locator("option")).toHaveText(["논문 본문", "현재 쪽"]);
  await input.fill("쓰던 질문");

  // 5) 머리의 3줄 요약: 새 대화에서 논문 본문으로 요약을 묻는다(범위 고르기와 상관없이)
  const before = fakeRuns().length;
  await page.getByRole("button", { name: "3줄 요약" }).click();
  await expect(lastTurn().locator(".chat-prompt")).toHaveText(/세 줄로 요약해 주세요/, { timeout: 15_000 });
  await expect(lastTurn().locator(".chat-answer strong").first()).toHaveText("가짜 답");
  const [summary] = fakeRuns().slice(before);
  expect(resumed(summary)).toBeNull();
  const summaryText = summary.message.message.content.at(-1)!.text!;
  expect(summaryText).toContain("## 질문 (요약)");
  expect(summaryText).toContain("- 범위: 논문 본문");
  await expect(input).toHaveValue("쓰던 질문"); // 쓰던 질문은 그대로다
  await expect(scope).toHaveValue("page");

  // 예전에 "선택만"을 골라 이 브라우저에 기억했으면 논문 본문으로 연다
  await page.evaluate(() => localStorage.setItem("paperloom.chat.scope", "selection"));
  await page.reload();
  await openPanel(page, "Claude와 대화");
  await expect(scope).toHaveValue("paper");
  await startNewChat(chat);
  const reopened = await askAndWait("범위 확인"); // 보이는 값만이 아니라 실제로 논문 본문을 보낸다
  expect(reopened.message.message.content.at(-1)!.text!).toContain("- 범위: 논문 본문");
});

test("사이드바 대화마다 이름을 바꾸고(Enter 저장·Esc 취소, 새로고침 뒤에도 남는다) 지운다", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "dpr-1", "대화 흐름은 DPR과 무관하다");
  await openPaper(page, "text-digital.pdf");
  await openPanel(page, "Claude와 대화");
  const chat = page.locator(CHAT);
  const input = chat.getByRole("textbox", { name: "질문" });
  const startChat = async (question: string) => {
    await startNewChat(chat);
    await input.fill(question);
    await input.press("Enter");
    await expect(chat.locator(".chat-turn:not(.is-pending)").last().locator(".chat-prompt")).toHaveText(question, { timeout: 15_000 });
  };
  const stamp = Date.now(); // 앞 실행의 대화와 구분한다
  await startChat(`이름 바꿀 대화 ${stamp}`);
  await startChat(`남길 대화 ${stamp}`);
  const openHistory = async () => {
    const toggle = chat.getByRole("button", { name: "대화 기록", exact: true });
    if ((await toggle.getAttribute("aria-expanded")) !== "true") await toggle.click();
  };
  await openHistory();
  const row = chat.locator(".chat-history-item", { hasText: `이름 바꿀 대화 ${stamp}` });
  const sessionId = (await row.getAttribute("data-session-id"))!;
  const byId = chat.locator(`.chat-history-item[data-session-id="${sessionId}"]`);

  // 1) 이름 바꾸기: Enter로 저장한다
  await byId.getByRole("button", { name: /이름 바꾸기$/ }).click();
  const field = chat.getByRole("textbox", { name: "대화 이름" });
  await field.fill("캐시 간섭 정리");
  await field.press("Enter");
  await expect(byId).toContainText("캐시 간섭 정리");
  // Esc는 고친 이름을 버린다(본문 강조 지우기로도 가지 않는다)
  await byId.getByRole("button", { name: /이름 바꾸기$/ }).click();
  await field.fill("버릴 이름");
  await field.press("Escape");
  await expect(byId).toContainText("캐시 간섭 정리");
  await expect(field).toHaveCount(0);

  // 2) 새로고침해도 이름이 남는다. 그 대화를 열면 지금 대화 이름도 같다
  await page.reload();
  await openPanel(page, "Claude와 대화");
  await openHistory();
  await expect(byId).toContainText("캐시 간섭 정리");
  await byId.locator("button").first().click();
  await expect(chat.locator(".chat-title")).toHaveText("캐시 간섭 정리");

  // 3) 지우기: 확인하면 대화와 그 답이 사라진다. 다른 대화는 남는다
  await openHistory();
  page.once("dialog", (dialog) => void dialog.accept());
  await byId.getByRole("button", { name: /지우기$/ }).click();
  await expect(byId).toHaveCount(0);
  await expect(chat.locator(".chat-history-item", { hasText: `남길 대화 ${stamp}` })).toHaveCount(1);
  const { answers } = await (await page.request.get(`/api/v1/answers?session_id=${sessionId}`)).json();
  expect(answers).toEqual([]);
});

test("답을 만드는 중에 중단하면 답을 저장하지 않고 질문을 입력칸에 돌려 둔다 (사이드바·원문 위 창)", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "dpr-1", "대화 흐름은 DPR과 무관하다");
  await openPaper(page, "text-digital.pdf");
  await openPanel(page, "Claude와 대화");
  const chat = page.locator(CHAT);
  await startNewChat(chat);
  const input = chat.getByRole("textbox", { name: "질문" });
  const answersBefore = (await (await page.request.get(`/api/v1/answers?origin=claude_code&limit=200`)).json()).answers.length;

  // 1) 사이드바: 보내면 보내기 단추가 중단 단추가 된다. 누르면 가짜 CLI가 기다리는 10초 안에 끝난다
  const started = Date.now();
  await input.fill("(느리게) 중단할 질문");
  await input.press("Enter");
  const stop = chat.getByRole("button", { name: "중단" });
  await expect(stop).toBeEnabled(); // 브리지가 실행 ID를 주었다
  await stop.click();
  await expect(chat.getByRole("status")).toContainText("중단했습니다");
  expect(Date.now() - started).toBeLessThan(9_000);
  await expect(input).toHaveValue("(느리게) 중단할 질문");
  await expect(chat.getByRole("button", { name: "보내기" })).toBeVisible();
  await expect(chat.locator(".chat-turn")).toHaveCount(0);

  // 2) 원문 위 질문 창도 중단한다
  await dragLine(page, 1, "epsilonword");
  await page.keyboard.press("Enter");
  const ask = page.getByRole("form", { name: "AI에게 질문" });
  await ask.getByRole("textbox", { name: "질문" }).fill("(느리게) 원문 위에서 중단");
  await ask.getByRole("textbox", { name: "질문" }).press("Enter");
  const thread = openWindow(page);
  await expect(thread.getByRole("button", { name: "중단" })).toBeEnabled();
  await thread.getByRole("button", { name: "중단" }).click();
  await expect(thread.locator(".status.error")).toHaveText("답 만들기를 중단했습니다.");
  await expect(thread.getByRole("button", { name: "중단" })).toHaveCount(0);

  const answersAfter = (await (await page.request.get(`/api/v1/answers?origin=claude_code&limit=200`)).json()).answers.length;
  expect(answersAfter).toBe(answersBefore); // 어느 쪽도 답을 저장하지 않았다
});

test("갈래: 지금 대화를 이어받은 새 대화로 묻고, 원래 대화는 그대로다. 컨텍스트 길이를 보인다", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "dpr-1", "대화 흐름은 DPR과 무관하다");
  const { paperId } = await openPaper(page, "text-digital.pdf");
  await openPanel(page, "Claude와 대화");
  const chat = page.locator(CHAT);
  const input = chat.getByRole("textbox", { name: "질문" });
  await startNewChat(chat);
  const stamp = Date.now();
  const lastPrompt = () => chat.locator(".chat-turn:not(.is-pending)").last().locator(".chat-prompt");
  await input.fill(`원래 질문 ${stamp}`);
  await input.press("Enter");
  await expect(lastPrompt()).toHaveText(`원래 질문 ${stamp}`, { timeout: 15_000 });
  const latest = await (await page.request.get(`/api/v1/answers?paper_id=${paperId}&origin=claude_code&limit=1`)).json();
  const original: string = latest.answers[0].session_id;
  // 컨텍스트 길이: 가짜 CLI는 3 + 1,200 + 800 + 50 토큰, 창 200,000
  // 입력칸 도구줄의 원형 아이콘. 숫자는 마우스를 올리면(title) 보이고 화면 낭독기는 이름으로 읽는다
  const ring = chat.locator(".chat-composer-bar").getByRole("img", { name: "컨텍스트 2,053 / 200,000 토큰 · 1%" });
  await expect(ring).toBeVisible();
  await expect(ring).toHaveAttribute("title", "컨텍스트 2,053 / 200,000 토큰 · 1%");
  // 한쪽(오른쪽 끝)으로: 범위·모델 칩 뒤, 보내기 단추 바로 왼쪽
  const ringBox = (await ring.boundingBox())!;
  const modelBox = (await chat.getByLabel("모델").boundingBox())!;
  const sendBox = (await chat.getByRole("button", { name: "보내기" }).boundingBox())!;
  expect(ringBox.x).toBeGreaterThan(modelBox.x + modelBox.width + 24);
  expect(sendBox.x - (ringBox.x + ringBox.width)).toBeLessThan(16);
  const originalTitle = (await chat.locator(".chat-title").textContent())!;

  // 1) 갈래 만들기: 원래 대화의 차례를 흐리게 이어받고, 이름은 "(갈래)"다
  await chat.getByRole("button", { name: "갈래 만들기" }).click();
  await expect(chat.locator(".chat-title")).toHaveText(`${originalTitle} (갈래)`);
  await expect(chat.locator(".chat-turn.is-inherited")).toHaveCount(1);
  await expect(chat.locator(".chat-turn.is-inherited").getByRole("button", { name: "버리기" })).toHaveCount(0);
  await expect(chat.locator(".chat-fork-divider")).toBeVisible();

  // 2) 갈래에서 물으면 --resume 원래 대화 --fork-session으로 질문만 보낸다(근거는 이어받은 대화에 있다)
  await input.fill(`갈래 질문 ${stamp}`);
  await input.press("Enter");
  await expect(lastPrompt()).toHaveText(`갈래 질문 ${stamp}`, { timeout: 15_000 });
  const run = fakeRuns().at(-1)!;
  expect(run.args).toContain("--fork-session");
  expect(resumed(run)).toBe(original);
  expect(run.message.message.content).toEqual([{ type: "text", text: `갈래 질문 ${stamp}` }]);
  await expect(chat.locator(".chat-turn.is-inherited")).toHaveCount(1);
  await expect(chat.locator(".chat-turn:not(.is-inherited)")).toHaveCount(1);

  // 3) 새로고침해도 갈래는 원래 대화를 이어받은 채이고, 원래 대화는 자기 차례만 있다
  await page.reload();
  await openPanel(page, "Claude와 대화");
  await chat.getByRole("button", { name: "대화 기록", exact: true }).click();
  const forkRow = chat.locator(".chat-history-item", { hasText: `${originalTitle} (갈래)` }).first();
  await forkRow.locator("button").first().click();
  await expect(chat.locator(".chat-turn.is-inherited .chat-prompt")).toHaveText(`원래 질문 ${stamp}`);
  await expect(chat.locator(".chat-turn:not(.is-inherited) .chat-prompt")).toHaveText(`갈래 질문 ${stamp}`);
  await chat.getByRole("button", { name: "대화 기록", exact: true }).click();
  await chat.locator(`.chat-history-item[data-session-id="${original}"]`).locator("button").first().click();
  await expect(chat.locator(".chat-turn .chat-prompt")).toHaveText([`원래 질문 ${stamp}`]);
});

test("답마다 갈래: 앞 답에서 가르면 그 답까지만 이어받는다(뒤 차례는 갈래에 없다)", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "dpr-1", "대화 흐름은 DPR과 무관하다");
  const { paperId } = await openPaper(page, "text-digital.pdf");
  await openPanel(page, "Claude와 대화");
  const chat = page.locator(CHAT);
  const input = chat.getByRole("textbox", { name: "질문" });
  await startNewChat(chat);
  const stamp = Date.now();
  for (const question of [`첫 질문 ${stamp}`, `둘째 질문 ${stamp}`]) {
    await input.fill(question);
    await input.press("Enter");
    await expect(chat.locator(".chat-turn:not(.is-pending)").last().locator(".chat-prompt")).toHaveText(question, { timeout: 15_000 });
  }
  const { answers } = await (await page.request.get(`/api/v1/answers?paper_id=${paperId}&origin=claude_code&limit=2`)).json();
  const [, first] = answers; // 최근 것부터

  // 첫 답의 "여기서 갈래": 첫 차례만 흐리게 이어받는다
  await chat.locator(`.chat-turn[data-answer-id="${first.answer_id}"]`).getByRole("button", { name: "여기서 갈래" }).click();
  await expect(chat.locator(".chat-turn.is-inherited .chat-prompt")).toHaveText([`첫 질문 ${stamp}`]);
  await input.fill(`갈래 질문 ${stamp}`);
  await input.press("Enter");
  await expect(chat.locator(".chat-turn:not(.is-pending):not(.is-inherited) .chat-prompt")).toHaveText([`갈래 질문 ${stamp}`], { timeout: 15_000 });
  const run = fakeRuns().at(-1)!;
  expect(resumed(run)).toBe(first.session_id);
  expect(run.args[run.args.indexOf("--resume-session-at") + 1]).toBe(first.message_id);
  expect(run.args).toContain("--fork-session");

  // 새로고침해도 갈래는 첫 차례까지만 이어받는다
  await page.reload();
  await openPanel(page, "Claude와 대화");
  await chat.getByRole("button", { name: "대화 기록", exact: true }).click();
  await chat.locator(".chat-history-item", { hasText: "(갈래)" }).first().locator("button").first().click();
  await expect(chat.locator(".chat-turn.is-inherited .chat-prompt")).toHaveText([`첫 질문 ${stamp}`]);
  await expect(chat.locator(".chat-turn:not(.is-inherited) .chat-prompt")).toHaveText([`갈래 질문 ${stamp}`]);
});

test("사이드바 왼쪽 경계를 끌어 너비를 바꾸고(새로고침해도 남는다) ←·→로도 바꾼다", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "dpr-1", "너비는 CSS px로 잰다");
  await openPaper(page, "text-digital.pdf");
  await openPanel(page, "Claude와 대화");
  const side = page.locator(".reader-side");
  const width = async () => (await side.boundingBox())!.width;
  const before = await width();
  const handle = page.getByRole("separator", { name: /사이드바 너비/ });
  const box = (await handle.boundingBox())!;
  await page.mouse.move(box.x + box.width / 2, box.y + 300);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width / 2 - 120, box.y + 300, { steps: 6 }); // 왼쪽으로 끌면 넓어진다
  await page.mouse.up();
  expect((await width()) - before).toBeCloseTo(120, 0);
  expect(await page.evaluate(() => document.getSelection()!.isCollapsed)).toBe(true); // 끄는 동안 글을 고르지 않았다
  const dragged = await width();

  await page.reload();
  await openPanel(page, "Claude와 대화");
  expect(await width()).toBeCloseTo(dragged, 0);
  await handle.focus();
  await page.keyboard.press("ArrowRight");
  expect(await width()).toBeCloseTo(dragged - 24, 0);
});

test("본문 옆 칩: 끌어 옮기고(누르기와 구분, 새로고침해도 남음) 고른 곳까지 선을 긋고, 메모가 있는 주석도 칩이 된다", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "dpr-1", "대화 흐름은 DPR과 무관하다");
  const { versionId } = await openPaper(page, "text-digital.pdf");
  await clearAnnotations(page, versionId);
  await page.reload();
  await expect(page.locator('.page[data-page-number="1"] .textLayer span').first()).toBeAttached();

  // 설명을 묻고 접어 칩으로 만든다
  await dragLine(page, 1, "epsilonword");
  await page.keyboard.press("e");
  const thread = openWindow(page);
  await expect(thread.locator(".chat-answer strong").first()).toHaveText("가짜 답", { timeout: 15_000 });
  const key = (await thread.getAttribute("data-thread-key"))!;
  await thread.getByRole("button", { name: "접기" }).click();
  const chip = page.locator(`.thread-chip[data-thread-key="${key}"]`);
  await expect(chip).toBeVisible();
  // 이 시험 자료에서는 칩이 처음에 고른 줄 위에 겹친다: 선을 긋지 않는다(마우스를 올리면 테두리로 보인다)
  const leader = page.locator(".chip-leader line");
  await expect(leader).toHaveCount(0);

  // 1) 마우스를 올리면 고른 곳에 테두리
  await chip.hover();
  await expect(page.locator(".chip-anchor-box")).toBeVisible();

  // 2) 끌어 옮긴다. 끈 것은 누름이 아니라 펼치지 않는다
  const before = (await chip.boundingBox())!;
  await page.mouse.move(before.x + 20, before.y + before.height / 2);
  await page.mouse.down();
  await page.mouse.move(before.x + 20 - 150, before.y + before.height / 2 + 80, { steps: 8 });
  await page.mouse.up();
  const after = (await chip.boundingBox())!;
  expect(after.x - before.x).toBeCloseTo(-150, 0);
  expect(after.y - before.y).toBeCloseTo(80, 0);
  // 칩이 고른 줄 아래로 갔다: 고른 줄 아래 끝에서 칩 위 가장자리 가운데로 선을 긋는다
  await expect(leader).toHaveCount(1);
  const ends = await leader.evaluate((line) => {
    const [x1, y1, x2, y2] = ["x1", "y1", "x2", "y2"].map((name) => Number(line.getAttribute(name)));
    const origin = line.closest(".inline-layer")!.getBoundingClientRect();
    return { start: { x: origin.left + x1, y: origin.top + y1 }, end: { x: origin.left + x2, y: origin.top + y2 } };
  });
  const lineBox = (await page.locator('.page[data-page-number="2"] .textLayer span', { hasText: "epsilonword" }).first().boundingBox())!;
  expect(ends.end.x).toBeCloseTo(after.x + after.width / 2, 0);
  expect(ends.end.y).toBeCloseTo(after.y, 0);
  expect(Math.abs(ends.start.y - (lineBox.y + lineBox.height))).toBeLessThan(3);
  expect(ends.start.x).toBeGreaterThanOrEqual(lineBox.x - 1);
  expect(ends.start.x).toBeLessThanOrEqual(lineBox.x + lineBox.width + 1);
  await page.mouse.move(after.x + 10, after.y + after.height / 2); // 마우스를 올리면 선이 진해진다
  await expect(page.locator(".chip-leader.is-active")).toHaveCount(1);
  await expect(openWindow(page)).toHaveCount(0);
  expect(await page.evaluate(() => document.getSelection()!.isCollapsed)).toBe(true);

  // 3) 새로고침해도 옮긴 자리다(대화 ID로 기억). 누르면 펼친다
  const scrolled = async () => chip.evaluate((element) => {
    const box = element.getBoundingClientRect();
    const page = element.closest(".reader-scroll")!.querySelector('.page[data-page-number="2"]')!.getBoundingClientRect();
    return { x: box.left - page.left, y: box.top - page.top };
  });
  const moved = await scrolled();
  await page.reload();
  const saved = page.locator(".thread-chip", { hasText: "답변 1" }).first();
  await expect(saved).toBeVisible();
  const restored = await saved.evaluate((element) => {
    const box = element.getBoundingClientRect();
    const page = element.closest(".reader-scroll")!.querySelector('.page[data-page-number="2"]')!.getBoundingClientRect();
    return { x: box.left - page.left, y: box.top - page.top };
  });
  expect(restored.x).toBeCloseTo(moved.x, 0);
  expect(restored.y).toBeCloseTo(moved.y, 0);
  await saved.click();
  await expect(openWindow(page)).toHaveCount(1);
  await openWindow(page).getByRole("button", { name: "접기" }).click();

  // 4) 메모가 있는 주석도 칩이 된다. 누르면 대화처럼 그 자리에서 펼치고(펼친 대화는 접는다), 접으면 다시 칩이다
  await dragLine(page, 1, "zetaword");
  await menuItem(page, "주석").click();
  await saveNote(page, "칩으로 보일 메모");
  const note = page.locator(".thread-chip.is-note", { hasText: "칩으로 보일 메모" });
  await expect(note).toBeVisible();
  await saved.click(); // 대화를 펼친 채로
  await expect(openWindow(page)).toHaveCount(1);
  await note.click();
  const noteWindow = page.locator(".inline-window.note-window");
  await expect(noteWindow).toContainText("칩으로 보일 메모");
  await expect(noteWindow.locator(".inline-original")).toContainText("zetaword");
  await expect(page.locator(".inline-window:not(.note-window)")).toHaveCount(0); // 한 번에 창 하나
  await expect(note).toHaveCount(0); // 펼친 동안 칩은 없다

  // 그 자리에서 메모를 고친다
  await noteWindow.getByRole("button", { name: "메모 고치기" }).click();
  await noteWindow.getByRole("textbox", { name: "메모" }).fill("고친 메모");
  await noteWindow.getByRole("button", { name: "저장" }).click();
  await expect(noteWindow.locator(".note-text")).toHaveText("고친 메모");

  // 접으면 고친 메모로 칩이 된다. 다시 펴서 주석 패널에서 볼 수도 있다
  await noteWindow.getByRole("button", { name: "접기" }).click();
  await expect(noteWindow).toHaveCount(0);
  const edited = page.locator(".thread-chip.is-note", { hasText: "고친 메모" });
  await expect(edited).toBeVisible();
  await edited.click();
  await page.locator(".inline-window.note-window").getByRole("button", { name: "주석 패널에서 보기" }).click();
  await expect(page.getByRole("button", { name: "주석", exact: true })).toHaveAttribute("aria-pressed", "true");
  await expect(page.locator(".note-item.is-focused")).toContainText("고친 메모");
});

test("문단 근거: 논문 본문의 문단마다 ¶를 달아 보내고, 답의 [근거 1¶2]를 누르면 그 문단을 강조한다", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "dpr-1", "대화 흐름은 DPR과 무관하다");
  const { paperId } = await openPaper(page, "text-digital.pdf");
  await openPanel(page, "Claude와 대화");
  const chat = page.locator(CHAT);
  await startNewChat(chat);
  await chat.getByLabel("범위").selectOption("paper");
  const input = chat.getByRole("textbox", { name: "질문" });
  await input.fill("(문단) 둘째 문단은 무엇을 말하나요?");
  await input.press("Enter");
  const chip = chat.locator(".chat-turn:not(.is-pending)").last().getByRole("button", { name: "근거 1¶2", exact: true });
  await expect(chip).toBeVisible({ timeout: 15_000 });
  await expect(chat.locator(".chat-answer").last()).not.toContainText("검토 전"); // 검토 전 표시는 뺐다 (W09 전까지)

  // 보낸 글: 논문 본문 근거의 문단마다 ¶번호
  const text = fakeRuns().at(-1)!.message.message.content.at(-1)!.text!;
  expect(text).toContain("> ¶1 Paperloom Extraction Sample");
  expect(text).toMatch(/> ¶2 /);
  expect(text).toContain("[근거 1¶2]"); // 그렇게 표시하라는 안내

  // 답의 근거는 근거 1의 둘째 문단 블록을 가리킨다
  const { answers } = await (await page.request.get(`/api/v1/answers?paper_id=${paperId}&origin=claude_code&limit=1`)).json();
  const paragraph = answers[0].citations.find((citation: { paragraph: number | null }) => citation.paragraph === 2);
  const packet = await (await page.request.get(`/api/v1/context-packets/${answers[0].packet_id}`)).json();
  expect(paragraph.block_id).toBe(packet.evidence[0].block_ids[1]);

  // 누르면 그 문단을 연다(쪽의 첫 문단이 아니라)
  await chip.click();
  await expect(page).toHaveURL(new RegExp(`page=1&block=${paragraph.block_id}`));
  await expect(page.locator('.page[data-page-number="1"] > .annotation-overlay > .quad-mark.is-focused').first()).toBeAttached();

  // 이어진 문단 범위 [근거 1¶3–4]도 단추이고 그 첫 문단을 연다 (2026-10-02 사용자 확인: 범위 표기는 링크가 안 됐다)
  await chat.locator(".chat-turn:not(.is-pending)").last().getByRole("button", { name: "근거 1¶3–4", exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`page=1&block=${packet.evidence[0].block_ids[2]}`));
});

test("수식이 섞인 글을 고르면 원문 이미지를 함께 보낸다", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "dpr-1", "대화 흐름은 DPR과 무관하다");
  await openPaper(page, "subscripts.pdf");
  const stacked = JSON.parse(readFileSync(new URL("subscripts.json", FIXTURE_DIR), "utf-8")).lines[0];
  await page.evaluate(([v0, v1]) => {
    const pageDiv = document.querySelector('.page[data-page-number="1"]')!;
    const frame = pageDiv.getBoundingClientRect();
    const spans = [...pageDiv.querySelectorAll(".textLayer span")].filter((span) => {
      const rect = span.getBoundingClientRect();
      const v = ((rect.top + rect.bottom) / 2 - frame.top) / frame.height;
      return rect.height > 0 && span.firstChild instanceof Text && v >= v0 && v <= v1;
    });
    const range = document.createRange();
    range.setStart(spans[0].firstChild!, 0);
    const last = spans.at(-1)!.firstChild!;
    range.setEnd(last, last.textContent!.length);
    document.getSelection()!.removeAllRanges();
    document.getSelection()!.addRange(range);
  }, stacked.v_range);
  await expect(page.locator(MENU)).toBeVisible();
  const runsBefore = fakeRuns().length;
  await menuItem(page, "설명").click();
  const thread = openWindow(page);
  await expect(thread.locator(".chat-answer")).toContainText("이미지 1개를 받았습니다", { timeout: 15_000 });
  await thread.locator(".evidence-toggle").click();
  await expect(thread.locator('li[data-role="selected_text"] img.evidence-image')).toBeVisible(); // 원문 수식 이미지를 보냈다
  const [run] = fakeRuns().slice(runsBefore);
  expect(run.message.message.content.map((block) => block.type)).toEqual(["image", "text"]);
  expect(run.message.message.content[1].text).toContain("수식이 섞여 있어 위 글자는 틀렸을 수 있습니다");
});

/** subscripts.pdf 1쪽 첫 줄(첨자가 쌓인 수식) 둘레를 Ctrl을 누른 채 끌어 영역으로 고른다. */
async function ctrlDragStacked(page: Page) {
  const [v0, v1] = JSON.parse(readFileSync(new URL("subscripts.json", FIXTURE_DIR), "utf-8")).lines[0].v_range;
  const frame = (await page.locator('.page[data-page-number="1"]').boundingBox())!;
  await page.keyboard.down("Control");
  await page.mouse.move(frame.x + frame.width * 0.1, frame.y + frame.height * (v0 - 0.01));
  await page.mouse.down();
  await page.mouse.move(frame.x + frame.width * 0.35, frame.y + frame.height * (v1 + 0.01), { steps: 6 });
  await page.mouse.up();
  await page.keyboard.up("Control");
  return { v0, v1 };
}

test("Ctrl을 누른 채 끌면 영역 모드 없이 바로 영역을 고르고, 종류를 수식으로 바꿔 설명을 묻는다", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "dpr-1", "대화 흐름은 DPR과 무관하다");
  await openPaper(page, "subscripts.pdf");
  await ctrlDragStacked(page);
  const toolbar = regionToolbar(page);
  await expect(toolbar).toBeVisible();
  await expect(page.locator(".reader-scroll.region-mode")).toHaveCount(0); // 영역 모드를 켜지 않았다
  await toolbar.locator("label.seg-opt", { hasText: /^수식$/ }).click();
  await expect(toolbar.getByRole("radio", { name: "수식" })).toBeChecked();
  const runsBefore = fakeRuns().length;
  await toolbar.getByRole("button", { name: /설명/ }).click();
  const thread = openWindow(page);
  await expect(thread.locator(".chat-answer")).toContainText("이미지 1개를 받았습니다", { timeout: 15_000 });
  await expect(thread.locator(".evidence-toggle")).toContainText("고른 수식");
  const [run] = fakeRuns().slice(runsBefore);
  expect(run.message.message.content[0].type).toBe("image");
  const text = run.message.message.content.at(-1)!.text!;
  expect(text).toContain("### [근거 1] 수식 영역 · ");
  expect(text).toContain("이 수식을 LaTeX로 옮기고, 각 기호의 뜻과 수식이 말하는 바를 설명해 주세요.");
  // 설명은 앞쪽부터 고른 쪽 다음 쪽까지의 본문을 함께 보낸다. 고른 영역이 먼저다 (2026-10-04 사용자 요청)
  expect(text).toMatch(/- 범위: 논문 본문 앞쪽부터 \d+쪽까지/);
  expect(text).toMatch(/### \[근거 \d+\] 논문 본문 · /);
  await thread.locator(".evidence-toggle").click();
  await expect(thread.locator('li[data-role="paper_text"]').first()).toBeVisible();
});

test("고른 표시와 링크로 연 위치의 강조는 Esc나 본문 빈 곳을 눌러 지운다", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "dpr-1", "대화 흐름은 DPR과 무관하다");
  await openPaper(page, "subscripts.pdf");
  const marks = page.locator('.page[data-page-number="1"] > .quad-overlay > .quad-mark');
  const focused = page.locator('.page[data-page-number="1"] > .annotation-overlay > .quad-mark.is-focused');
  /** 고른 줄 오른쪽의 빈 곳(글·그림·창이 없다)을 끌지 않고 누른다 */
  const clickBeside = async ({ v0, v1 }: { v0: number; v1: number }) => {
    const frame = (await page.locator('.page[data-page-number="1"]').boundingBox())!;
    await page.mouse.click(frame.x + frame.width * 0.9, frame.y + (frame.height * (v0 + v1)) / 2);
  };

  // 1) Ctrl로 끈 영역은 Esc로 지운다
  const line = await ctrlDragStacked(page);
  await expect(regionToolbar(page)).toBeVisible();
  await expect(marks).toHaveCount(1);
  await page.keyboard.press("Escape");
  await expect(marks).toHaveCount(0);
  await expect(regionToolbar(page)).toHaveCount(0);

  // 2) 다시 골라 설명을 묻고 답의 "근거 1"을 누르면 그 영역이 강조된다. 창을 접고 본문 빈 곳을 누르면 강조와 주소의 위치가 사라진다
  await ctrlDragStacked(page);
  await regionToolbar(page).getByRole("button", { name: /설명/ }).click();
  const thread = openWindow(page);
  await expect(thread.locator(".chat-answer")).toContainText("이미지 1개를 받았습니다", { timeout: 15_000 });
  await thread.getByRole("button", { name: "근거 1", exact: true }).first().click();
  await expect(page).toHaveURL(/anchor=/);
  await expect(focused).toHaveCount(1);
  const key = (await thread.getAttribute("data-thread-key"))!;
  await thread.getByRole("button", { name: "접기" }).click();
  await clickBeside(line);
  await expect(focused).toHaveCount(0);
  await expect(page).not.toHaveURL(/anchor=/);

  // 3) Esc도 링크로 연 위치의 강조를 지운다
  await page.locator(`.thread-chip[data-thread-key="${key}"]`).click();
  await openWindow(page).getByRole("button", { name: "근거 1", exact: true }).first().click();
  await expect(focused).toHaveCount(1);
  await page.keyboard.press("Escape");
  await expect(focused).toHaveCount(0);
  await expect(page).not.toHaveURL(/anchor=/);
  await openWindow(page).getByRole("button", { name: "접기" }).click();

  // 4) 글 선택도 본문 빈 곳을 누르면 표시와 메뉴가 사라진다
  const plain = page.locator('.page[data-page-number="1"] .textLayer span', { hasText: "NO SCRIPTS HERE" }).first();
  await plain.scrollIntoViewIfNeeded();
  await plain.evaluate((span) => {
    const range = document.createRange();
    range.selectNodeContents(span);
    document.getSelection()!.removeAllRanges();
    document.getSelection()!.addRange(range);
  });
  await expect(page.locator(MENU)).toBeVisible();
  await expect(marks).not.toHaveCount(0);
  const frame = (await page.locator('.page[data-page-number="1"]').boundingBox())!;
  const plainBox = (await plain.boundingBox())!;
  await page.mouse.click(frame.x + frame.width * 0.9, plainBox.y + plainBox.height / 2);
  await expect(marks).toHaveCount(0);
  await expect(page.locator(MENU)).toHaveCount(0);
});

test("브리지가 꺼져 있으면 서재·Reader 머리에 꺼짐을 글로 알리고, 누르면 설정에서 켜는 명령을 보인다", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "dpr-1", "DPR과 무관하다");
  await page.route("http://127.0.0.1:8794/**", (route) => route.abort());
  await page.goto("/");
  await expect(page.locator(".library-head .bridge-indicator")).toHaveText("Claude Code 꺼짐");
  await page.locator(".library-head .bridge-indicator").click();
  const settings = page.getByRole("dialog", { name: "설정" });
  await expect(settings.locator('[data-bridge="offline"]')).toContainText("브리지가 꺼져 있습니다");
  await expect(settings.locator(".config-snippet")).toContainText("-m paperloom.integrations.claude_code");
  await page.keyboard.press("Escape");
  await expect(settings).toHaveCount(0);

  await openPaper(page, "text-digital.pdf");
  await expect(page.locator(".bridge-indicator")).toHaveText("Claude Code 꺼짐");
  await openPanel(page, "Claude와 대화");
  await expect(page.locator(CHAT).locator('[data-bridge="offline"]')).toBeVisible();
  await page.getByRole("textbox", { name: "질문" }).fill("보내지 않는 질문");
  await expect(page.locator(CHAT).getByRole("button", { name: "보내기" })).toBeDisabled();
});
