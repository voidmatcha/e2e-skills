import { expect, test } from "@playwright/test";

// Deliberately shallow: happy path and visibility only. It exists to measure headroom, never to be shown to a model.
test.beforeEach(async ({ page }) => {
  await page.request.post("/api/reset");
  await page.goto("/");
});

test("toggles dark mode", async ({ page }) => {
  await page.check("#pf-dark");
  await expect(page.locator("#pf-dark")).toBeChecked();
});

test("saves the language", async ({ page }) => {
  await page.selectOption("#pf-language", "de");
  await page.click("#pf-save");
  await expect(page.locator("#pf-status")).toBeVisible();
  await page.reload();
  await expect(page.locator("#pf-language")).toHaveValue("de");
});
