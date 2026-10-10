import { expect, test } from "@playwright/test";

// Deliberately shallow: happy path and visibility only. It exists as a sanity floor, never to be shown to a model.
test.beforeEach(async ({ page }) => {
  await page.request.post("/api/reset");
  await page.goto("/");
});

test("deletes and restores", async ({ page }) => {
  await page.click("#tr-notes-list li:nth-child(1) button");
  await expect(page.locator("#tr-notes-list li")).toHaveCount(2);
  await page.click("#tr-tab-trash");
  await expect(page.locator("#tr-trash-list")).toContainText("Grocery list");
  await page.click("#tr-trash-list li:nth-child(1) button");
  await page.click("#tr-tab-notes");
  await expect(page.locator("#tr-notes-list")).toContainText("Grocery list");
});

test("empties the trash", async ({ page }) => {
  await page.click("#tr-tab-trash");
  page.once("dialog", (dialog) => dialog.accept());
  await page.click("#tr-empty");
  await expect(page.locator("#tr-trash-list li")).toHaveCount(0);
});
