import { expect, test } from "@playwright/test";

test("shows the overdue banner for the current patron", async ({ page }) => {
  await page.goto("/patrons/CARD-552");
  await expect(page.getByTestId("overdue-banner")).toBeVisible();
});
