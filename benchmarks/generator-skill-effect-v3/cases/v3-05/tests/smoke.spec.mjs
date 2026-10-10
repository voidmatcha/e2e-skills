import { expect, test } from "@playwright/test";

test("shows the builder heading", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Survey builder" })).toBeVisible();
});
