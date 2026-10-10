import { expect, test } from "@playwright/test";

// Deliberately shallow: happy path and visibility only. It exists as a sanity floor, never to be shown to a model.
test.beforeEach(async ({ page }) => {
  await page.request.post("/api/reset");
  await page.goto("/");
});

test("saves a new name", async ({ page }) => {
  await page.fill("#pf-name", "Grace Hopper");
  await page.click("#pf-form button");
  await expect(page.locator("#pf-status")).toContainText("saved");
  await expect(page.locator("#pf-header-name")).toHaveText("Grace Hopper");
});

test("rejects a short name", async ({ page }) => {
  await page.fill("#pf-name", "A");
  await page.click("#pf-form button");
  await expect(page.locator("#pf-error")).toBeVisible();
});
