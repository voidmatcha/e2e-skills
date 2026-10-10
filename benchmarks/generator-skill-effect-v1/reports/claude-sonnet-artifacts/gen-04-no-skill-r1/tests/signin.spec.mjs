import { expect, test } from "@playwright/test";

const signIn = async (page, email, code) => {
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Access code").fill(code);
  await page.getByRole("button", { name: "Sign in" }).click();
};

test.beforeEach(async ({ page, request }) => {
  await request.post("/api/reset");
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
});

test("demo account sees the dashboard", async ({ page }) => {
  await signIn(page, "ada@example.com", "4471");
  await expect(page.getByText("Welcome, Ada")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Sign in" })).toBeHidden();
});

test("wrong access code keeps the form and shows an error", async ({ page }) => {
  await signIn(page, "ada@example.com", "0000");
  await expect(page.getByRole("alert")).toHaveText("Invalid email or access code");
  await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
  await expect(page.getByText("Welcome, Ada")).toBeHidden();
});

test("missing email shows an error", async ({ page }) => {
  await signIn(page, "", "4471");
  await expect(page.getByRole("alert")).toHaveText("Email is required");
  await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
});

test("session survives a reload", async ({ page }) => {
  await signIn(page, "ada@example.com", "4471");
  await expect(page.getByText("Welcome, Ada")).toBeVisible();
  await page.reload();
  await expect(page.getByText("Welcome, Ada")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Sign in" })).toBeHidden();
});

test("sign out returns to the form and ends the session", async ({ page }) => {
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
