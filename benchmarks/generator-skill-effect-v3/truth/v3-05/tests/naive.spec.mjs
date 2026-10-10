import { expect, test } from "@playwright/test";

// Deliberately shallow and id-based: it exists as a sanity floor and must fail the markup refactor; never shown to a model.
test.beforeEach(async ({ page }) => {
  await page.request.post("/api/reset");
  await page.goto("/");
});

test("adds an option", async ({ page }) => {
  await page.fill("#sb-questions .question:nth-child(1) .add-option input", "Podcast");
  await page.click("#sb-questions .question:nth-child(1) .add-option button");
  await expect(page.locator("#sb-questions .question:nth-child(1) li")).toHaveCount(4);
});

test("opens the preview", async ({ page }) => {
  await page.click("#sb-preview-toggle");
  await expect(page.locator("#sb-preview")).toBeVisible();
});
