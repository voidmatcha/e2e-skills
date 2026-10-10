import { expect, test } from "@playwright/test";

// Deliberately shallow and id-based: it exists as a sanity floor and must fail the markup refactor; never shown to a model.
test.beforeEach(async ({ page }) => {
  await page.request.post("/api/reset");
  await page.goto("/");
});

test("assigns an issue", async ({ page }) => {
  await page.click("#is-list .issue:nth-child(2) button");
  await expect(page.locator("#is-list .issue:nth-child(2) .assignee")).toHaveText("Assigned to Ada");
});

test("filters mine", async ({ page }) => {
  await page.click("#is-filters .chip:nth-child(2)");
  await expect(page.locator("#is-list .issue")).toHaveCount(1);
});
