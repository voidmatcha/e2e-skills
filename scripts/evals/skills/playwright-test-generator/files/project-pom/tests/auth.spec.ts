import { test, expect } from "@playwright/test";
import { LoginPage } from "./pages/login-page";

test.describe("Authentication", () => {
  test("signs in with valid credentials and lands on the dashboard", async ({ page }) => {
    const loginPage = new LoginPage(page);
    await loginPage.open();
    await loginPage.login("user@example.test", "correct-horse-battery-staple");

    await expect(page).toHaveURL(/\/dashboard/);
    await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
  });

  test("shows an error for invalid credentials", async ({ page }) => {
    const loginPage = new LoginPage(page);
    await loginPage.open();
    await loginPage.login("user@example.test", "wrong-password");

    await expect(loginPage.errorMessage).toBeVisible();
    await expect(page).toHaveURL(/\/login/);
  });
});
