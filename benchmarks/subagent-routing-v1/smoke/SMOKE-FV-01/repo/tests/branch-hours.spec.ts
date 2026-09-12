import { expect, test } from "@playwright/test";

test.only("shows the library branch hours", async ({ page }) => {
  await page.goto("/branch-hours");
  await expect(page.getByRole("heading", { name: "Library branch hours" })).toBeVisible();
});
