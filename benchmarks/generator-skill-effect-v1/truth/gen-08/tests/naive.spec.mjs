import { expect, test } from "@playwright/test";

// Deliberately shallow: happy path and visibility only. It exists to measure headroom, never to be shown to a model.
test.beforeEach(async ({ page }) => {
  await page.request.post("/api/reset");
  await page.goto("/");
});

test("votes", async ({ page }) => {
  await page.check("#pl-choice-vim");
  await page.click("#pl-vote");
  await expect(page.getByText("Thanks for voting")).toBeVisible();
  await expect(page.locator("#pl-tally")).toContainText("Vim");
});
