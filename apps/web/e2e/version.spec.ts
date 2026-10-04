/**
 * 새 빌드 알림 (2026-10-04 사용자 확인: 다시 빌드한 뒤 열려 있던 탭이 옛 웹앱을 계속 돌려 번역 표시 <sub>가 글자 그대로 보였다).
 * 서버의 index.html 진입 스크립트가 이 탭의 것과 다르면(다시 빌드됨) 새로고침하라는 띠를 보인다. 다시 빌드하는 대신 "/" 응답을 바꿔 흉내 낸다.
 */
import { expect, test } from "@playwright/test";

test("다시 빌드되면(서버 index.html의 진입 스크립트가 다르면) 탭이 다시 보일 때 새로고침 띠를 보이고, 누르면 새로 불러온다", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "dpr-1", "알림은 DPR과 무관하다");
  await page.goto("/");
  await expect(page.locator(".shelf-table")).toBeVisible();
  const banner = page.getByRole("status").filter({ hasText: "새로 빌드되었습니다" });

  // 같은 빌드면 아무것도 보이지 않는다
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await page.waitForLoadState("networkidle");
  await expect(banner).toHaveCount(0);

  // 서버가 다른 진입 스크립트를 주면(다시 빌드됨) 탭이 다시 보일 때 띠를 보인다
  await page.route("/", async (route) => {
    if (route.request().resourceType() !== "fetch") return route.continue();
    const response = await route.fetch();
    const html = (await response.text()).replace(/\/assets\/index-[^"]+\.js/, "/assets/index-NEWBUILD.js");
    await route.fulfill({ response, body: html });
  });
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await expect(banner).toBeVisible();

  // 새로고침을 누르면 새로 불러오고(서버가 다시 이 빌드를 주면) 띠가 사라진다
  await page.unroute("/");
  await Promise.all([page.waitForEvent("load"), banner.getByRole("button", { name: "새로고침" }).click()]);
  await expect(page.locator(".shelf-table")).toBeVisible();
  await expect(banner).toHaveCount(0);
});
