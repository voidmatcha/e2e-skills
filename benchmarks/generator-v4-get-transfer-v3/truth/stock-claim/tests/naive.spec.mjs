import { expect, test } from "@playwright/test";

test("shows inventory choices", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("#claim-list")).toContainText("Lamp");
  await expect(page.locator("#claim-list")).toContainText("Desk");
});
