import { expect, test } from "@playwright/test";

// Deliberately shallow: happy path and visibility only. It exists as a sanity floor, never to be shown to a model.
test.beforeEach(async ({ page }) => {
  await page.goto("/");
});

test("sorts by name", async ({ page }) => {
  await page.click("#iv-sort-name");
  await expect(page.locator("#iv-rows tr:first-child td:first-child")).toContainText("Anvil");
  await expect(page.locator("#iv-rows tr:last-child td:first-child")).toContainText("Froe");
});

test("shows out of stock", async ({ page }) => {
  await expect(page.getByText("Out of stock").first()).toBeVisible();
});
