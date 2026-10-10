import { expect, test } from "@playwright/test";

test("shows the reading list heading", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Reading list" })).toBeVisible();
});
