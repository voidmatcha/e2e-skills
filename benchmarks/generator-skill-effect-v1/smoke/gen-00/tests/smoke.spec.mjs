import { expect, test } from "@playwright/test";

test("shows the calculator heading", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Tip calculator" })).toBeVisible();
});
