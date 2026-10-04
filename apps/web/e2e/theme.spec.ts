/**
 * 테마 (docs/UI_PLAN.md A13): 어두운 판·밝은 판 모두에서 글자가 바탕과 구분된다.
 *
 * 2026-10-02 사용자 확인: 다크 모드에서 대화 패널의 범위·모델 목록을 펼치면 흰 바탕에 옅은 글자가 나왔다. 브라우저 기본
 * 드롭다운은 Windows에서 투명한 바탕을 흰색으로 그리는데, 글자색은 테마의 밝은 색을 물려받았기 때문이다.
 * 펼친 목록은 운영체제가 그리므로 스크린샷으로 잴 수 없다. 대신 목록 항목(option)의 계산된 바탕이 불투명하고
 * 글자와의 대비가 WCAG AA(4.5:1) 이상인지 본다.
 */
import { expect, test } from "@playwright/test";

import { openFixture } from "./fixture";

type Rgba = [number, number, number, number];

for (const colorScheme of ["dark", "light"] as const) {
  test(`${colorScheme === "dark" ? "어두운" : "밝은"} 판: Reader의 펼침 목록 항목은 불투명한 바탕에 읽을 수 있는 글자다`, async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== "dpr-1", "색은 DPR과 무관하다");
    await page.emulateMedia({ colorScheme });
    await openFixture(page);
    const options = await page.evaluate(() =>
      [...document.querySelectorAll("select")].flatMap((select) =>
        [...select.options].map((option) => {
          const style = getComputedStyle(option);
          return { select: select.getAttribute("aria-label"), option: option.textContent, color: style.color, background: style.backgroundColor };
        }),
      ),
    );
    expect(options.map((item) => item.select)).toEqual(expect.arrayContaining(["범위", "모델"]));
    for (const item of options) {
      const background = parse(item.background);
      expect(background[3], `${item.select} › ${item.option} 바탕이 투명하다`).toBe(1);
      expect(contrast(parse(item.color), background), `${item.select} › ${item.option} 대비`).toBeGreaterThanOrEqual(4.5);
    }
  });
}

function parse(css: string): Rgba {
  const [r, g, b, a = 1] = css.match(/[\d.]+/g)!.map(Number);
  return [r, g, b, a];
}

/** WCAG 2.1 대비 (글자가 불투명하다고 본다) */
function contrast(foreground: Rgba, background: Rgba): number {
  const luminance = ([r, g, b]: Rgba) => {
    const channel = (value: number) => {
      const c = value / 255;
      return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
    };
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
  };
  const [lighter, darker] = [luminance(foreground), luminance(background)].sort((a, b) => b - a);
  return (lighter + 0.05) / (darker + 0.05);
}
