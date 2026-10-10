import { expect, test } from "@playwright/test";

test.beforeEach(async ({ request }) => {
  await request.post("/api/reset");
});

const emailFor = (name) => `${name}@example.com`;

const lastCode = async (request) => {
  const response = await request.get("/api/dev/last-code");
  expect(response.ok()).toBeTruthy();
  return response.json();
};

const wrongCodeFor = (code) => {
  const firstDigit = code[0] === "0" ? "1" : "0";
  return `${firstDigit}${code.slice(1)}`;
};

const requestCode = async (page, email) => {
  await page.goto("/");
  await page.getByLabel("Email").fill(email);
  await Promise.all([
    page.waitForResponse((response) => response.url().endsWith("/api/codes") && response.request().method() === "POST"),
    page.getByRole("button", { name: "Send code" }).click(),
  ]);
  await expect(page.getByRole("status")).toHaveText(`We sent a code to ${email}`);
};

test("signs in with an emailed code, survives reload, and signs out", async ({ page, request }) => {
  const email = emailFor("visitor");

  await requestCode(page, email);
  const issued = await lastCode(request);
  expect(issued).toEqual({ email, code: expect.stringMatching(/^\d{6}$/) });

  await page.getByLabel("Code").fill(issued.code);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByText(`Signed in as ${email}`)).toBeVisible();

  await page.reload();
  await expect(page.getByText(`Signed in as ${email}`)).toBeVisible();

  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page.getByLabel("Email")).toBeVisible();
  await expect(page.getByRole("button", { name: "Send code" })).toBeVisible();
});

test("rejects a wrong code and locks a code after three wrong attempts", async ({ page, request }) => {
  const email = emailFor("lockout");

  await requestCode(page, email);
  const issued = await lastCode(request);
  const wrongCode = wrongCodeFor(issued.code);

  await page.getByLabel("Code").fill(wrongCode);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("alert")).toHaveText("That code is not right");

  await page.getByLabel("Code").fill(wrongCode);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("alert")).toHaveText("That code is not right");

  await page.getByLabel("Code").fill(wrongCode);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("alert")).toHaveText("Too many attempts. Request a new code.");

  await page.getByLabel("Code").fill(issued.code);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("alert")).toHaveText("Too many attempts. Request a new code.");

  await Promise.all([
    page.waitForResponse((response) => response.url().endsWith("/api/codes") && response.request().method() === "POST"),
    page.getByRole("button", { name: "Request a new code" }).click(),
  ]);

  const fresh = await lastCode(request);
  expect(fresh.email).toBe(email);

  await page.getByLabel("Code").fill(wrongCodeFor(fresh.code));
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("alert")).toHaveText("That code is not right");

  await page.getByLabel("Code").fill(fresh.code);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByText(`Signed in as ${email}`)).toBeVisible();
});
