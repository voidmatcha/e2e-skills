import { expect, test } from "@playwright/test";

// Deliberately shallow: happy path and visibility only. It exists as a sanity floor, never to be shown to a model.
test.beforeEach(async ({ page }) => {
  await page.request.post("/api/reset");
  await page.goto("/");
});

test("deletes a selected file", async ({ page }) => {
  await page.check("#fm-rows tr:nth-child(1) input");
  page.once("dialog", (dialog) => dialog.accept());
  await page.click("#fm-delete");
  await expect(page.locator("#fm-rows tr")).toHaveCount(6);
  await expect(page.locator("#fm-toast")).toBeVisible();
});

test("undo restores", async ({ page }) => {
  await page.check("#fm-rows tr:nth-child(1) input");
  page.once("dialog", (dialog) => dialog.accept());
  await page.click("#fm-delete");
  await page.click("#fm-undo");
  await expect(page.locator("#fm-rows tr")).toHaveCount(7);
});
