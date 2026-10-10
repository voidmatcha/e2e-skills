import { expect, test } from "@playwright/test";

// Deliberately shallow and id-based: it exists as a sanity floor and must fail the markup refactor; never shown to a model.
test.beforeEach(async ({ page }) => {
  await page.request.post("/api/reset");
  await page.goto("/");
});

test("plays a track", async ({ page }) => {
  await page.click("#pl-tracks li:nth-child(2) button:nth-of-type(1)");
  await expect(page.locator("#pl-now")).toBeVisible();
  await expect(page.locator("#pl-now-title")).toHaveText("So What");
});

test("removes a track", async ({ page }) => {
  await page.click("#pl-tracks li:nth-child(1) button:last-child");
  await expect(page.locator("#pl-tracks li")).toHaveCount(3);
  await expect(page.locator(".total")).toContainText("Total");
});
