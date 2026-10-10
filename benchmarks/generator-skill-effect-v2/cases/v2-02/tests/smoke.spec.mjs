import { expect, test } from "@playwright/test";

test("shows the search heading", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Library search" })).toBeVisible();
});
