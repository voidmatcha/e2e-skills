import { expect, test } from "@playwright/test";

test("shows saved choices", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("#saved-list")).toContainText("Oak");
  await expect(page.locator("#saved-list")).toContainText("Cedar");
});
