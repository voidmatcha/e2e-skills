import { expect, test } from "@playwright/test";

test("shows the sign-in heading", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
});
