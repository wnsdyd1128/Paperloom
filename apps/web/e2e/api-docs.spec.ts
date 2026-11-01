import { expect, test } from "@playwright/test";

test("API 문서: /docs가 외부로 나가지 않고 열려 태그와 오류 설명을 보인다", async ({ page, baseURL }) => {
  const requested: string[] = [];
  const failed: string[] = [];
  page.on("request", (request) => requested.push(request.url()));
  page.on("pageerror", (error) => failed.push(error.message));

  await page.goto("/docs");

  const exportTag = page.locator("#operations-tag-Wiki로_내보내기");
  await expect(exportTag).toBeVisible();
  await expect(page.locator(".opblock-tag")).toHaveCount(12);

  await page.locator("#operations-Wiki로_내보내기-create_bundle_api_v1_evidence_bundles_post button.opblock-summary-control").click();
  const responses = page.locator(".responses-table").first();
  await expect(responses).toContainText("OUTBOX_UNAVAILABLE");
  await expect(responses).toContainText("같은 키·같은 본문의 재전송");

  const outside = requested.filter((url) => !url.startsWith(`${baseURL}/`) && !url.startsWith("data:"));
  expect(outside).toEqual([]);
  expect(failed).toEqual([]);
});
