import { expect, test } from "@playwright/test";

test("shows the newsletter heading", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Newsletter" })).toBeVisible();
});
