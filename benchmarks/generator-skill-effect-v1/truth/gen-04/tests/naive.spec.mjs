import { expect, test } from "@playwright/test";

// Deliberately shallow: happy path and visibility only. It exists to measure headroom, never to be shown to a model.
test.beforeEach(async ({ page }) => {
  await page.request.post("/api/reset");
  await page.goto("/");
});

test("signs in", async ({ page }) => {
  await page.fill("#si-email", "ada@example.com");
  await page.fill("#si-code", "4471");
  await page.click("button[type=submit]");
  await expect(page.getByText("Welcome, Ada")).toBeVisible();
});

test("signs out", async ({ page }) => {
  await page.fill("#si-email", "ada@example.com");
  await page.fill("#si-code", "4471");
  await page.click("button[type=submit]");
  await page.click("#si-signout");
  await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
});
