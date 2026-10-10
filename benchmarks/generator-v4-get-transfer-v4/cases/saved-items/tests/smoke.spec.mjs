import { expect, test } from "@playwright/test";

test("shows saved items", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Saved items" })).toBeVisible();
});
