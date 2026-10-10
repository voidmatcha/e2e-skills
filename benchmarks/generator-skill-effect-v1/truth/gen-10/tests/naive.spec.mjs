import { expect, test } from "@playwright/test";

// Deliberately shallow: happy path and visibility only. It exists to measure headroom, never to be shown to a model.
test.beforeEach(async ({ page }) => {
  await page.goto("/");
});

test("shows the first page", async ({ page }) => {
  await expect(page.getByText("Record 1", { exact: true })).toBeVisible();
  await expect(page.locator("#pg-status")).toHaveText("Page 1 of 3");
});

test("goes to the next page", async ({ page }) => {
  await page.click("#pg-next");
  await expect(page.getByText("Record 11", { exact: true })).toBeVisible();
});
