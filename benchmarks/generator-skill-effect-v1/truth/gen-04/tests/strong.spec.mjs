import { expect, test } from "@playwright/test";

async function signIn(page, email, code) {
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Access code").fill(code);
  await page.getByRole("button", { name: "Sign in" }).click();
}

test.beforeEach(async ({ page }) => {
  await page.request.post("/api/reset");
  await page.goto("/");
});

test("signs in to the dashboard", async ({ page }) => {
  await signIn(page, "ada@example.com", "4471");
  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
  await expect(page.getByText("Welcome, Ada")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Sign in" })).toBeHidden();
});

test("rejects a wrong access code", async ({ page }) => {
  await signIn(page, "ada@example.com", "0000");
  await expect(page.getByRole("alert")).toHaveText("Invalid email or access code");
  await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeHidden();
});

test("requires an email", async ({ page }) => {
  await signIn(page, "", "4471");
  await expect(page.getByRole("alert")).toHaveText("Email is required");
});

test("keeps the session across a reload", async ({ page }) => {
  await signIn(page, "ada@example.com", "4471");
  await expect(page.getByText("Welcome, Ada")).toBeVisible();
  await page.reload();
  await expect(page.getByText("Welcome, Ada")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Sign in" })).toBeHidden();
});

test("sign out ends the session on the server", async ({ page }) => {
  await signIn(page, "ada@example.com", "4471");
  await expect(page.getByText("Welcome, Ada")).toBeVisible();
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
  await page.reload();
  await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeHidden();
});
