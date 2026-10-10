import { expect, test } from "@playwright/test";

// Deliberately shallow and id-based: it exists as a sanity floor and must fail the markup refactor; never shown to a model.
test.beforeEach(async ({ page }) => {
  await page.request.post("/api/reset");
  await page.goto("/");
});

test("adds an item", async ({ page }) => {
  await page.fill("#sl-add-input", "Coffee");
  await page.click("#sl-add-form button");
  await expect(page.locator("#sl-list li")).toHaveCount(4);
  await expect(page.locator("#sl-status")).toContainText("4 items");
});

test("marks an item bought", async ({ page }) => {
  await page.check("#sl-list li:nth-child(2) input");
  await expect(page.locator(".status-line")).toContainText("1 bought");
});
