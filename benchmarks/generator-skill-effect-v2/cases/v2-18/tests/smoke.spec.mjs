import { expect, test } from "@playwright/test";

test("shows the settings heading", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Notification settings" })).toBeVisible();
});
