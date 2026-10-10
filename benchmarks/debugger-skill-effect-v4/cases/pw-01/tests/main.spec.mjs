
import { test, expect } from "@playwright/test";

test.describe("signed-in shell", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
    await page.click("#sign-in");
  });

  test("shows the account name", async ({ page }) => {
    await expect(page.locator("#who")).toHaveText("Signed in as sam");
  });

  test("links to orders", async ({ page }) => {
    await expect(page.locator("#orders")).toBeVisible();
  });

  test("offers log out", async ({ page }) => {
    await expect(page.locator("#logout")).toBeVisible();
  });

  test("hides the login button", async ({ page }) => {
    await expect(page.locator("#login")).toBeHidden();
  });
});
