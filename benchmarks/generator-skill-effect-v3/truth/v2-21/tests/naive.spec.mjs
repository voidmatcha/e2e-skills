import { expect, test } from "@playwright/test";

// Deliberately shallow: happy path and visibility only. It exists as a sanity floor, never to be shown to a model.
test.beforeEach(async ({ page }) => {
  await page.request.post("/api/reset");
  await page.goto("/");
});

test("switches to german", async ({ page }) => {
  await page.selectOption("#ln-language", "de");
  await expect(page.locator("#ln-title")).toHaveText("Versionshinweise");
});
