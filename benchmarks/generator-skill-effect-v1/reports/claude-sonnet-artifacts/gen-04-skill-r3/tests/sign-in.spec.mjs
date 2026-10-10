import { expect, test } from "@playwright/test";

const DEMO = { email: "ada@example.com", code: "4471" };

test.describe("sign-in portal", () => {
  test.beforeEach(async ({ page, request }) => {
    // Drop every server-side session so each test starts signed out.
    const reset = await request.post("/api/reset");
    expect(reset.ok()).toBeTruthy();
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
  });

  const signIn = async (page, email, code) => {
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Access code").fill(code);
    await page.getByRole("button", { name: "Sign in" }).click();
  };

  test("signing in with the demo account shows the dashboard", async ({ page }) => {
    await signIn(page, DEMO.email, DEMO.code);

    await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
    await expect(page.getByText("Welcome, Ada")).toBeVisible();
    await expect(page.getByRole("heading", { name: "Sign in" })).toBeHidden();
  });

  test("a wrong access code keeps the form and shows an error", async ({ page }) => {
    await signIn(page, DEMO.email, "0000");

    await expect(page.getByRole("alert")).toHaveText("Invalid email or access code");
    await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Dashboard" })).toBeHidden();
  });

  test("submitting without an email shows an error", async ({ page }) => {
    await page.getByLabel("Access code").fill(DEMO.code);
    await page.getByRole("button", { name: "Sign in" }).click();

    await expect(page.getByRole("alert")).toHaveText("Email is required");
    await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
  });

  test("a signed-in session survives a reload", async ({ page }) => {
    await signIn(page, DEMO.email, DEMO.code);
    await expect(page.getByText("Welcome, Ada")).toBeVisible();

    await page.reload();

    await expect(page.getByText("Welcome, Ada")).toBeVisible();
    await expect(page.getByRole("heading", { name: "Sign in" })).toBeHidden();
  });

  test("signing out returns to the form and ends the session on the server", async ({ page, context }) => {
    await signIn(page, DEMO.email, DEMO.code);
    await expect(page.getByText("Welcome, Ada")).toBeVisible();
    const [sid] = (await context.cookies()).filter((c) => c.name === "sid");
    expect(sid).toBeDefined();

    await page.getByRole("button", { name: "Sign out" }).click();
    await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();

    // The server clears the cookie too, so put the old one back: only a
    // server-side session end keeps the form showing after a reload.
    await context.addCookies([sid]);
    await page.reload();

    await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Dashboard" })).toBeHidden();
  });
});
