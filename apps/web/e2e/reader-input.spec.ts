/**
 * W03a · Reader 입력 조작 (IMPL §10.5, G2 R12).
 *
 * 1) Ctrl+휠: 커서 아래의 PDF 지점이 제자리에 남고, 저장된 선택 표시가 새 배율에서 글자와 맞는다(A03 기준).
 *    휠 이벤트가 취소되어 브라우저 자체 확대가 일어나지 않고, 본문 밖(머리·사이드바)의 Ctrl+휠은 가로채지 않는다.
 *
 * 브라우저 자체 확대는 이벤트 취소(defaultPrevented)로 확인한다. Playwright에서는 취소하지 않은 Ctrl+휠·Ctrl+=도
 * 브라우저 확대를 일으키지 않아(devicePixelRatio·innerWidth 불변, G2 W03a 기록) 확대 결과로는 확인할 수 없다.
 * 2) Ctrl+±·Ctrl+0과 머리의 축소·확대 단추는 같은 preset 단계를 쓴다. Reader가 열려 있으면 포커스 위치와 무관하게 받고,
 *    Library 화면에서는 가로채지 않는다. 확대 뒤에도 본문 포커스가 유지된다.
 * 3) 열자마자, 그리고 본문을 클릭한 뒤 PageDown·Space·Home·End·방향키가 본문을 스크롤한다.
 */
import { expect, type Page, test } from "@playwright/test";

import { EXPECTED, MAX_REPROJECTION_ERROR_PX, openFixture, reprojectionError, selectAndRead, setView, TARGETS, zoomButton } from "./fixture";

// 확대 뒤 커서 아래 PDF 지점이 움직인 거리(축별). 스크롤 위치는 정수 CSS px로 맞춰지므로 한 번의 반올림
// (0.5 px)만 허용한다. 이벤트마다 지점을 새로 잡으면 반올림 오차가 쌓여 이 기준을 넘는다.
const MAX_PIN_SHIFT_PX = 0.51;
// 핀치처럼 작은 Ctrl+휠이 이어지는 경우. DPR 1에서는 합이 휠 세 칸(deltaY -300)이다.
const WHEEL_EVENTS = 12;
const WHEEL_DELTA_Y = -25;
// 커서를 둘 페이지 안 위치(폭·높이 비율). 확대 뒤 스크롤로 되돌릴 수 있는 곳이어야 한다: 왼쪽 여백 근처는
// 필요한 scrollLeft가 음수가 되어 고정할 수 없다(IMPL §10.5).
const PIN_FRACTION = { x: 0.6, y: 0.3 };

type RecordedEvent = { key?: string; ctrlKey: boolean; deltaY?: number; defaultPrevented: boolean };

test("Ctrl+휠: 커서 아래 지점이 제자리에 남고 선택 표시가 글자와 맞는다", async ({ page }, testInfo) => {
  await openFixture(page);
  await setView(page, 0, 1);
  const target = TARGETS[0];
  await selectAndRead(page, target);
  await page.evaluate(() => document.getSelection()?.removeAllRanges()); // 저장된 quad만 남긴다
  await recordEvents(page, "wheel");

  const pageDiv = page.locator('.page[data-page-number="1"]');
  const before = (await pageDiv.boundingBox())!;
  // MouseEvent.clientX·Y는 정수 CSS px이므로 앱이 받는 좌표와 같도록 정수 위치에 둔다.
  const pointer = {
    x: Math.round(before.x + before.width * PIN_FRACTION.x),
    y: Math.round(before.y + before.height * PIN_FRACTION.y),
  };
  const fraction = { x: (pointer.x - before.x) / before.width, y: (pointer.y - before.y) / before.height };
  await page.mouse.move(pointer.x, pointer.y);
  await page.keyboard.down("Control");
  for (let index = 0; index < WHEEL_EVENTS; index++) await page.mouse.wheel(0, WHEEL_DELTA_Y);
  await page.keyboard.up("Control");

  // 휠 한 칸(deltaY 100 CSS px)마다 1.2배. 브라우저가 전달한 deltaY 합으로 기대 배율을 구한다.
  const wheels = await recordedEvents(page, "wheel");
  const deltaSum = wheels.reduce((sum, event) => sum + event.deltaY!, 0);
  const zoom = zoomButton(page);
  const zoomValue = async () => Number(await zoom.getAttribute("data-zoom"));
  await expect.poll(zoomValue).toBeCloseTo(1.2 ** (-deltaSum / 100), 3);
  const scale = await zoomValue();
  expect(scale).toBeGreaterThan(1.15);
  await expect(zoom).toHaveText(`${Math.round(scale * 100)}%`); // 목록 밖 배율도 지금 값으로 보인다
  expect(wheels.every((event) => event.ctrlKey && event.defaultPrevented), "Ctrl+휠이 모두 취소됨").toBe(true);

  const after = (await pageDiv.boundingBox())!;
  const pinShift = {
    x: after.x + after.width * fraction.x - pointer.x,
    y: after.y + after.height * fraction.y - pointer.y,
  };
  expect(Math.abs(pinShift.x), "커서 아래 지점 가로 이동(px)").toBeLessThanOrEqual(MAX_PIN_SHIFT_PX);
  expect(Math.abs(pinShift.y), "커서 아래 지점 세로 이동(px)").toBeLessThanOrEqual(MAX_PIN_SHIFT_PX);

  const error = await reprojectionError(page, target, 0, scale);
  expect(error).toBeLessThanOrEqual(MAX_REPROJECTION_ERROR_PX);

  // Reader 본문 밖(머리·사이드바)의 Ctrl+휠은 브라우저에 맡긴다.
  for (const selector of [".reader-header", ".reader-side"]) {
    const canceled = await page.locator(selector).evaluate(
      (element) =>
        !element.dispatchEvent(new WheelEvent("wheel", { ctrlKey: true, deltaY: -100, bubbles: true, cancelable: true })),
    );
    expect(canceled, selector).toBe(false);
  }
  await expect(zoom).toHaveAttribute("data-zoom", String(scale));

  // 같은 칸만큼 축소하면 원래 배율로 돌아온다.
  await page.mouse.move(pointer.x, pointer.y);
  await page.keyboard.down("Control");
  for (let index = 0; index < WHEEL_EVENTS; index++) await page.mouse.wheel(0, -WHEEL_DELTA_Y);
  await page.keyboard.up("Control");
  await expect.poll(zoomValue).toBeCloseTo(1, 2);

  const summary = { project: testInfo.project.name, deltaY: wheels.map((event) => event.deltaY), scale, pinShift, error };
  console.log(`W03a wheel ${JSON.stringify(summary)}`);
  await testInfo.attach("w03a-wheel-summary", { body: JSON.stringify(summary, null, 2), contentType: "application/json" });
});

test("Ctrl+±·Ctrl+0과 머리 단추가 같은 단계로 확대한다", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "dpr-1", "키 입력 처리는 DPR과 무관하다");
  await openFixture(page);
  const zoom = zoomButton(page);
  await expect(zoom).toHaveAttribute("data-zoom", "1");
  await expect(page.locator(".reader-scroll")).toBeFocused();
  await recordEvents(page, "keydown");

  const steps: [string, string][] = [
    ["Control+Equal", "1.1"],
    ["Control+Shift+Equal", "1.25"], // "+"
    ["Control+Minus", "1.1"],
    ["Control+Digit0", "1"],
    ["Control+Minus", "0.9"],
  ];
  for (const [keys, value] of steps) {
    await page.keyboard.press(keys);
    await expect(zoom, keys).toHaveAttribute("data-zoom", value);
  }
  const zoomKeys = (await recordedEvents(page, "keydown")).filter((event) => !["Control", "Shift"].includes(event.key!));
  expect(zoomKeys.map((event) => event.key)).toEqual(["=", "+", "-", "0", "-"]);
  expect(zoomKeys.every((event) => event.defaultPrevented), "단축키가 모두 취소됨").toBe(true);

  // 머리 단추는 같은 단계를 쓴다. 포커스가 머리에 있어도 Reader 안이므로 단축키가 작동한다.
  const zoomIn = page.getByRole("button", { name: "확대" });
  const zoomOut = page.getByRole("button", { name: "축소" });
  await zoomIn.click();
  await expect(zoom).toHaveAttribute("data-zoom", "1");
  await zoomIn.click();
  await expect(zoom).toHaveAttribute("data-zoom", "1.1");
  await zoomOut.click();
  await expect(zoom).toHaveAttribute("data-zoom", "1");
  await page.keyboard.press("Control+Minus");
  await expect(zoom).toHaveAttribute("data-zoom", "0.9");
  await page.keyboard.press("Control+Digit0");
  await expect(zoom).toHaveAttribute("data-zoom", "1");

  // 본문을 클릭한 뒤 확대해도 포커스가 본문에 남는다. PDF.js가 다시 그리며 숨기는 text layer가 포커스를
  // 받으면 body로 빠져, 다음 단축키가 브라우저 자체 확대가 되던 문제의 회귀 방지.
  const scroller = page.locator(".reader-scroll");
  await scroller.locator('.page[data-page-number="1"]').click({ position: { x: 300, y: 300 } });
  await expect(scroller).toBeFocused();
  await page.keyboard.press("Control+Equal");
  await expect(zoom).toHaveAttribute("data-zoom", "1.1");
  await expect(page.locator('.page[data-page-number="1"] .textLayer:not([hidden])')).toBeAttached();
  await expect(scroller).toBeFocused();

  // Reader가 열려 있으면 포커스가 없어도(body) PDF 배율을 바꾼다.
  const dispatchCtrlEqual = () =>
    page.evaluate(() => {
      (document.activeElement as HTMLElement | null)?.blur();
      return !document.body.dispatchEvent(
        new KeyboardEvent("keydown", { key: "=", ctrlKey: true, bubbles: true, cancelable: true }),
      );
    });
  expect(await dispatchCtrlEqual()).toBe(true);
  await expect(zoom).toHaveAttribute("data-zoom", "1.25");

  // Library 화면에서는 브라우저에 맡긴다.
  await page.getByRole("button", { name: "서재로 돌아가기" }).click();
  await expect(zoom).toHaveCount(0);
  expect(await dispatchCtrlEqual()).toBe(false);
});

test("열자마자 키보드로 본문을 스크롤한다", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "dpr-1", "키보드 스크롤은 DPR과 무관하다");
  await openFixture(page);
  const scroller = page.locator(".reader-scroll");
  await expect(scroller).toBeFocused();
  const metrics = () =>
    scroller.evaluate((element) => ({
      top: element.scrollTop,
      fromBottom: element.scrollHeight - element.clientHeight - element.scrollTop,
      height: element.clientHeight,
    }));
  const { height } = await metrics();
  const pageInput = page.getByLabel("쪽 번호");
  const lastPage = EXPECTED.pages.length;

  await page.keyboard.press("PageDown");
  await expect.poll(async () => (await metrics()).top).toBeGreaterThan(height / 2);
  // 브라우저는 뒤쪽 페이지 크기를 읽는 대로 문서 높이를 늘리므로 끝은 "바닥까지 남은 거리"로 확인한다.
  await page.keyboard.press("End");
  await expect.poll(async () => (await metrics()).fromBottom).toBeLessThan(1);
  await expect(pageInput).toHaveValue(`${lastPage}`);
  await expect(page.locator(".page-box")).toHaveAttribute("data-pages", `${lastPage}`);
  await page.keyboard.press("Home");
  await expect.poll(async () => (await metrics()).top).toBe(0);
  await expect(pageInput).toHaveValue("1");
  await page.keyboard.press("Space");
  await expect.poll(async () => (await metrics()).top).toBeGreaterThan(height / 2);
  await page.keyboard.press("Shift+Space");
  await expect.poll(async () => (await metrics()).top).toBe(0);
  await page.keyboard.press("ArrowDown");
  await expect.poll(async () => (await metrics()).top).toBeGreaterThan(0);
  expect((await metrics()).top).toBeLessThan(height / 2);

  // 머리로 포커스가 옮겨 가도 본문을 클릭하면 다시 키보드로 이동할 수 있다.
  await page.getByRole("button", { name: "서재로 돌아가기" }).focus();
  await scroller.locator('.page[data-page-number="1"]').click({ position: { x: 20, y: 200 } });
  await expect(scroller).toBeFocused();
  await page.keyboard.press("End");
  await expect.poll(async () => (await metrics()).fromBottom).toBeLessThan(1);
});

/**
 * window까지 올라온 이벤트가 앞선 처리에서 취소됐는지 기록한다. 페이지가 취소한 Ctrl+휠·확대 단축키는
 * 브라우저 자체 확대를 일으키지 않는다.
 */
async function recordEvents(page: Page, type: "wheel" | "keydown") {
  await page.evaluate((type) => {
    const log: RecordedEvent[] = [];
    Object.assign(window, { [`__${type}`]: log });
    window.addEventListener(
      type,
      (event) => {
        const { key, ctrlKey } = event as KeyboardEvent; // WheelEvent에도 ctrlKey가 있다
        log.push({ key, ctrlKey, deltaY: (event as WheelEvent).deltaY, defaultPrevented: event.defaultPrevented });
      },
      { passive: true },
    );
  }, type);
}

async function recordedEvents(page: Page, type: "wheel" | "keydown"): Promise<RecordedEvent[]> {
  return page.evaluate((type) => (window as unknown as Record<string, RecordedEvent[]>)[`__${type}`], type);
}
