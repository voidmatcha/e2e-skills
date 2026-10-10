import { expect, test } from "@playwright/test";

const demo = { email: "ada@example.com", code: "4471" };

test.beforeEach(async ({ page, request }) => {
  const reset = await request.post("/api/reset");
  expect(reset.ok()).toBe(true);
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
});

async function signIn(page, email, code) {
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Access code").fill(code);
  await page.getByRole("button", { name: "Sign in" }).click();
}

async function signInAsDemo(page) {
  await signIn(page, demo.email, demo.code);
  await expect(page.getByText("Welcome, Ada")).toBeVisible();
}

test("signing in with the demo account shows the dashboard", async ({ page }) => {
  await signIn(page, demo.email, demo.code);

  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
  await expect(page.getByText("Welcome, Ada")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Sign in" })).toBeHidden();
  await expect(page.getByLabel("Email")).toBeHidden();
});

test("a wrong access code keeps the form and shows an error", async ({ page }) => {
  await signIn(page, demo.email, "0000");

  await expect(page.getByRole("alert")).toHaveText("Invalid email or access code");
  await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeHidden();
});

test("submitting without an email shows an error", async ({ page }) => {
  await page.getByLabel("Access code").fill(demo.code);
  await page.getByRole("button", { name: "Sign in" }).click();

  await expect(page.getByRole("alert")).toHaveText("Email is required");
  await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeHidden();
});

test("a signed-in session survives a reload", async ({ page }) => {
  await signInAsDemo(page);

  await page.reload();

  await expect(page.getByText("Welcome, Ada")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Sign in" })).toBeHidden();
});

test("signing out returns to the form and ends the server session", async ({ page }) => {
  await signInAsDemo(page);

  await page.getByRole("button", { name: "Sign out" }).click();

  await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeHidden();

  await page.reload();

  await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
  await expect(page.getByText("Welcome, Ada")).toBeHidden();
});
