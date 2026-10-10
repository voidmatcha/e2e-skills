import { expect, test } from "@playwright/test";

// Deliberately shallow and id-based: it exists as a sanity floor and must fail the markup refactor; never shown to a model.
test.beforeEach(async ({ page }) => {
  await page.request.post("/api/reset");
  await page.goto("/");
});

test("adds a recipe to the plan", async ({ page }) => {
  await page.click("#rc-cards .card:nth-child(1) .controls button:last-child");
  await expect(page.locator("#rc-plan")).toContainText("1 recipe");
});

test("filters by tag", async ({ page }) => {
  await page.click("#rc-tags .chip:nth-child(3)");
  await expect(page.locator("#rc-cards .card")).toHaveCount(1);
});
