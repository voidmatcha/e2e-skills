import { expect, test } from "@playwright/test";

test("shows the address book heading", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Address book" })).toBeVisible();
});
