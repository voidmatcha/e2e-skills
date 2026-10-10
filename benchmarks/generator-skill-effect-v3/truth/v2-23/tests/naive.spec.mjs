import { expect, test } from "@playwright/test";

// Deliberately shallow: happy path and visibility only. It exists as a sanity floor, never to be shown to a model.
test.beforeEach(async ({ page }) => {
  await page.request.post("/api/reset");
  await page.goto("/");
});

test("deletes the account", async ({ page }) => {
  await page.click("#ac-open");
  await page.fill("#ac-confirm-text", "DELETE");
  await page.click("#ac-confirm");
  await expect(page.locator("#ac-gone")).toBeVisible();
});

test("cancel closes the dialog", async ({ page }) => {
  await page.click("#ac-open");
  await page.click("#ac-cancel");
  await expect(page.locator("#ac-dialog")).toBeHidden();
});
