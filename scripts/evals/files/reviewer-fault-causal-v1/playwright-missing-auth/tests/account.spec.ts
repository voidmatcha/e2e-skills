import { expect, test } from "@playwright/test";

test("opens the authenticated account surface", async ({ page }) => {
  await page.goto("/account");
  await expect(page.getByRole("heading", { name: "Account" })).toBeVisible();
});

test("shows the authenticated member identity", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("fixture-auth", "valid"));
  await page.goto("/account");
  await expect(page.getByTestId("account-name")).toHaveText("Ada Lovelace");
});
