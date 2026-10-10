import { expect, test } from "@playwright/test";

const resetState = async ({ request }) => {
  await request.post("/api/reset");
};

const requestCode = async (page, email) => {
  await page.getByLabel("Email").fill(email);
  await page.getByRole("button", { name: "Send code" }).click();
  await expect(page.getByText(`We sent a code to ${email}`)).toBeVisible();
};

const lastCode = async (request) => {
  const response = await request.get("/api/dev/last-code");
  expect(response.ok()).toBeTruthy();
  return response.json();
};

const submitCode = async (page, code) => {
  await page.getByLabel("Code").fill(code);
  await page.getByRole("button", { name: "Sign in" }).click();
};

test.beforeEach(resetState);

test("signs in with an emailed code, survives reload, and signs out", async ({ page, request }) => {
  const email = "visitor@example.com";

  await page.goto("/");
  await requestCode(page, email);

  const issued = await lastCode(request);
  expect(issued).toEqual({ email, code: expect.stringMatching(/^\d{6}$/) });

  await submitCode(page, issued.code);
  await expect(page.getByText(`Signed in as ${email}`)).toBeVisible();

  await page.reload();
  await expect(page.getByText(`Signed in as ${email}`)).toBeVisible();

  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
  await expect(page.getByLabel("Email")).toBeVisible();
});

test("rejects wrong codes, locks a code after three attempts, and accepts a fresh code", async ({ page, request }) => {
  const email = "locked@example.com";

  await page.goto("/");
  await requestCode(page, email);
  const firstCode = (await lastCode(request)).code;

  await submitCode(page, "000000" === firstCode ? "000001" : "000000");
  await expect(page.getByRole("alert")).toHaveText("That code is not right");

  await submitCode(page, "111111" === firstCode ? "111112" : "111111");
  await expect(page.getByRole("alert")).toHaveText("That code is not right");

  await submitCode(page, "222222" === firstCode ? "222223" : "222222");
  await expect(page.getByRole("alert")).toHaveText("Too many attempts. Request a new code.");

  await submitCode(page, firstCode);
  await expect(page.getByRole("alert")).toHaveText("Too many attempts. Request a new code.");

  await page.getByRole("button", { name: "Request a new code" }).click();
  await expect(page.getByText(`We sent a code to ${email}`)).toBeVisible();

  const freshCode = (await lastCode(request)).code;
  await submitCode(page, freshCode);
  await expect(page.getByText(`Signed in as ${email}`)).toBeVisible();
});
