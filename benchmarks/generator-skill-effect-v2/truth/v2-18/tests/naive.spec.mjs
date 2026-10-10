import { expect, test } from "@playwright/test";

// Deliberately shallow: happy path and visibility only. It exists as a sanity floor, never to be shown to a model.
test.beforeEach(async ({ page }) => {
  await page.request.post("/api/reset");
  await page.goto("/");
});

test("shows and dismisses a toast", async ({ page }) => {
  await page.click("#nt-send");
  await expect(page.locator("#nt-region .toast")).toHaveCount(1);
  await page.click("#nt-region .toast button");
  await expect(page.locator("#nt-region .toast")).toHaveCount(0);
});
