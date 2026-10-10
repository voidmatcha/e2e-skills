import { expect, test } from "@playwright/test";

test.beforeEach(async ({ request }) => {
  await request.post("/api/reset");
});

async function signIn(page, email, code) {
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Access code").fill(code);
  await page.getByRole("button", { name: "Sign in" }).click();
}

test("demo account signs in and sees the dashboard", async ({ page }) => {
  await page.goto("/");
  await signIn(page, "ada@example.com", "4471");
  await expect(page.getByText("Welcome, Ada")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Sign in" })).toBeHidden();
});

test("wrong access code shows an error and keeps the form", async ({ page }) => {
  await page.goto("/");
  await signIn(page, "ada@example.com", "0000");
  await expect(page.getByRole("alert")).toHaveText("Invalid email or access code");
  await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
  await expect(page.getByText("Welcome, Ada")).toBeHidden();
});

test("missing email shows a validation error", async ({ page }) => {
  await page.goto("/");
  await signIn(page, "", "4471");
  await expect(page.getByRole("alert")).toHaveText("Email is required");
  await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
});

test("session survives a reload", async ({ page }) => {
  await page.goto("/");
  await signIn(page, "ada@example.com", "4471");
  await expect(page.getByText("Welcome, Ada")).toBeVisible();
  await page.reload();
  await expect(page.getByText("Welcome, Ada")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Sign in" })).toBeHidden();
});

test("sign out returns to the form and ends the server session", async ({ page }) => {
  await page.goto("/");
  await signIn(page, "ada@example.com", "4471");
  await expect(page.getByText("Welcome, Ada")).toBeVisible();
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
  await page.reload();
  await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
  await expect(page.getByText("Welcome, Ada")).toBeHidden();
  const res = await page.request.get("/api/session");
  expect(res.status()).toBe(401);
});
