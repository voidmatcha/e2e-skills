import { expect, test } from "@playwright/test";

// Deliberately shallow and id-based: it exists as a sanity floor and must fail the markup refactor; never shown to a model.
test.beforeEach(async ({ page }) => {
  await page.request.post("/api/reset");
  await page.goto("/");
});

test("selects a seat", async ({ page }) => {
  await page.click("#sp-grid .seat-row:nth-child(1) .seat:nth-child(2)");
  await expect(page.locator("#sp-selected")).toHaveText("Selected: A2");
});

test("reserves", async ({ page }) => {
  await page.click("#sp-grid .seat-row:nth-child(1) .seat:nth-child(2)");
  await page.click("#sp-reserve");
  await expect(page.locator("#sp-confirmation")).toContainText("Reserved A2");
});
