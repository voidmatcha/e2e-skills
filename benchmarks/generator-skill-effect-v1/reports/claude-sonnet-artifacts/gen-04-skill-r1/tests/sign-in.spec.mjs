import { expect, test } from "@playwright/test";

const demo = { email: "ada@example.com", code: "4471" };

test.beforeEach(async ({ page, request }) => {
  // POST /api/reset is the test seam that drops every server-side session.
  const reset = await request.post("/api/reset");
  expect(reset.ok()).toBe(true);
  await page.goto("/");
});

const signInForm = (page) => page.getByRole("heading", { name: "Sign in" });
const emailInput = (page) => page.getByLabel("Email");
const codeInput = (page) => page.getByLabel("Access code");
const submitButton = (page) => page.getByRole("button", { name: "Sign in" });
const dashboardHeading = (page) => page.getByRole("heading", { name: "Dashboard" });

async function signIn(page, email, code) {
  await emailInput(page).fill(email);
  await codeInput(page).fill(code);
  await submitButton(page).click();
}

test("signing in with the demo account shows the dashboard greeting", async ({ page }) => {
  const request = page.waitForRequest((r) => r.method() === "POST" && new URL(r.url()).pathname === "/api/session");
  await signIn(page, demo.email, demo.code);
  expect((await request).postDataJSON()).toEqual(demo);

  await expect(dashboardHeading(page)).toBeVisible();
  await expect(page.getByText("Welcome, Ada")).toBeVisible();
  await expect(signInForm(page)).toBeHidden();
});

test("a wrong access code keeps the sign-in form and shows an error", async ({ page }) => {
  await signIn(page, demo.email, "0000");

  await expect(page.getByRole("alert")).toHaveText("Invalid email or access code");
  await expect(signInForm(page)).toBeVisible();
  await expect(dashboardHeading(page)).toBeHidden();
});

test("submitting without an email shows an error", async ({ page }) => {
  await codeInput(page).fill(demo.code);
  await submitButton(page).click();

  await expect(page.getByRole("alert")).toHaveText("Email is required");
  await expect(signInForm(page)).toBeVisible();
});

test("a signed-in session survives a reload", async ({ page }) => {
  await signIn(page, demo.email, demo.code);
  await expect(page.getByText("Welcome, Ada")).toBeVisible();

  await page.reload();

  await expect(page.getByText("Welcome, Ada")).toBeVisible();
  await expect(signInForm(page)).toBeHidden();
});

test("signing out returns to the form and ends the session on the server", async ({ page, context }) => {
  await signIn(page, demo.email, demo.code);
  await expect(page.getByText("Welcome, Ada")).toBeVisible();
  const signedInCookies = await context.cookies();
  expect(signedInCookies.map((c) => c.name)).toContain("sid");

  const signedOut = page.waitForRequest((r) => r.method() === "DELETE" && new URL(r.url()).pathname === "/api/session");
  await page.getByRole("button", { name: "Sign out" }).click();
  await signedOut;
  await expect(signInForm(page)).toBeVisible();

  // Sign out also expires the cookie in the browser, so put the old sid back:
  // the form can only still show if the server itself dropped that session.
  await context.addCookies(signedInCookies);
  await page.reload();

  await expect(signInForm(page)).toBeVisible();
  await expect(dashboardHeading(page)).toBeHidden();
});
