import { expect, test } from "@playwright/test";

// Deliberately shallow: happy path and visibility only. It exists as a sanity floor, never to be shown to a model.
test.beforeEach(async ({ page }) => {
  await page.request.post("/api/reset");
  await page.goto("/");
});

test("autosaves and publishes", async ({ page }) => {
  await page.fill("#ed-title", "Hello");
  await expect(page.locator("#ed-status")).toContainText("saved", { ignoreCase: true });
  await page.click("#ed-publish");
  await expect(page.locator("#ed-posts")).toContainText("Hello");
});

test("discards", async ({ page }) => {
  await page.fill("#ed-title", "Draft");
  await page.click("#ed-discard");
  await expect(page.locator("#ed-title")).toHaveValue("");
});
