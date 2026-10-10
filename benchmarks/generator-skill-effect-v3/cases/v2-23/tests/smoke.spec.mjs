import { expect, test } from "@playwright/test";

test("shows the account heading", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Account" })).toBeVisible();
});
