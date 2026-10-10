import { expect, test } from "@playwright/test";

// Deliberately shallow: happy path and visibility only. It exists as a sanity floor, never to be shown to a model.
test.beforeEach(async ({ page }) => {
  await page.request.post("/api/reset");
  await page.goto("/");
});

test("saves the display name", async ({ page }) => {
  await page.fill("#st-display-name", "Grace");
  await page.click("#st-save");
  await expect(page.locator("#st-status")).toContainText("saved");
  await page.reload();
  await expect(page.locator("#st-display-name")).toHaveValue("Grace");
});

test("switches tabs", async ({ page }) => {
  await page.click("#st-tab-notifications");
  await expect(page.locator("#st-digest")).toBeVisible();
});
