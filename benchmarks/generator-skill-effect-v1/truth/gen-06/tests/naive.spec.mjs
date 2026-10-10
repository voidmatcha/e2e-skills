import { expect, test } from "@playwright/test";

// Deliberately shallow: happy path and visibility only. It exists to measure headroom, never to be shown to a model.
test.beforeEach(async ({ page }) => {
  await page.request.post("/api/reset");
  await page.goto("/");
});

test("marks a task done", async ({ page }) => {
  await page.click("#tb-open li:nth-child(2) button");
  await expect(page.locator("#tb-done")).toContainText("Book flights");
});

test("undoes a task", async ({ page }) => {
  await page.click("#tb-open li:nth-child(1) button");
  await expect(page.locator("#tb-done")).toContainText("Write report");
  await page.click("#tb-done li:nth-child(1) button");
  await expect(page.locator("#tb-open")).toContainText("Write report");
});
