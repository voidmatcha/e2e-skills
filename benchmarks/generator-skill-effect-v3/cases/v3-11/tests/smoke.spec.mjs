import { expect, test } from "@playwright/test";

test("shows the thread heading", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: /Release thread/ })).toBeVisible();
});
