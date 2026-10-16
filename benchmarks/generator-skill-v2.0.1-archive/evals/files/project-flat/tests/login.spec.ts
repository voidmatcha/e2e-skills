import { test, expect } from "@playwright/test";

// Flat spec style: direct page.goto + page.getByX calls, no Page Object Model.

test.describe("Login", () => {
  test("signs in with valid credentials", async ({ page }) => {
    await page.goto("/login");
    await page.getByLabel("Email").fill("user@example.test");
    await page.getByLabel("Password").fill("correct-horse-battery-staple");
    await page.getByRole("button", { name: "Sign in" }).click();

    await expect(page).toHaveURL(/\/dashboard/);
  });

  test("shows an error for invalid credentials", async ({ page }) => {
    await page.goto("/login");
    await page.getByLabel("Email").fill("user@example.test");
    await page.getByLabel("Password").fill("wrong-password");
    await page.getByRole("button", { name: "Sign in" }).click();

    await expect(page.getByText("Invalid credentials")).toBeVisible();
  });
});
