import { expect, test } from "@playwright/test";

test("shows queue labels", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("#priority-list")).toContainText("Raven");
  await expect(page.locator("#priority-list")).toContainText("Finch");
});
