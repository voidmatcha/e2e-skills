import { expect, test } from "@playwright/test";

test.beforeEach(async ({ request }) => {
  await request.post("/api/reset");
});

const requestCode = async (page, request, email) => {
  await page.goto("/");
  await page.getByLabel("Email").fill(email);
  await page.getByRole("button", { name: "Send code", exact: true }).click();
  await expect(page.getByRole("status")).toHaveText(`We sent a code to ${email}`);

  const response = await request.get("/api/dev/last-code");
  const lastCode = await response.json();
  expect(lastCode.email).toBe(email);
  return lastCode.code;
};

const wrongCodeFor = (code) => (code === "000000" ? "111111" : "000000");

test("signs in with an emailed code, persists after reload, and signs out", async ({ page, request }) => {
  const email = "visitor@example.com";
  const code = await requestCode(page, request, email);

  await page.getByLabel("Code").fill(code);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();

  await expect(page.getByText(`Signed in as ${email}`)).toBeVisible();

  await page.reload();
  await expect(page.getByText(`Signed in as ${email}`)).toBeVisible();

  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Sign in", exact: true })).toBeVisible();
  await expect(page.getByLabel("Email")).toBeVisible();
});

test("shows an error for a wrong code", async ({ page, request }) => {
  const code = await requestCode(page, request, "wrong-code@example.com");

  await page.getByLabel("Code").fill(wrongCodeFor(code));
  await page.getByRole("button", { name: "Sign in", exact: true }).click();

  await expect(page.getByRole("alert")).toHaveText("That code is not right");
});

test("locks a code after three wrong attempts and accepts a newly requested code", async ({ page, request }) => {
  const email = "locked-code@example.com";
  const code = await requestCode(page, request, email);
  const wrongCode = wrongCodeFor(code);

  for (let attempt = 0; attempt < 2; attempt += 1) {
    await page.getByLabel("Code").fill(wrongCode);
    await page.getByRole("button", { name: "Sign in", exact: true }).click();
    await expect(page.getByRole("alert")).toHaveText("That code is not right");
  }

  await page.getByLabel("Code").fill(wrongCode);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.getByRole("alert")).toHaveText("Too many attempts. Request a new code.");

  await page.getByLabel("Code").fill(code);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.getByRole("alert")).toHaveText("Too many attempts. Request a new code.");

  await page.getByRole("button", { name: "Request a new code", exact: true }).click();
  await expect(page.getByRole("status")).toHaveText(`We sent a code to ${email}`);

  const response = await request.get("/api/dev/last-code");
  const freshCode = (await response.json()).code;

  await page.getByLabel("Code").fill(freshCode);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.getByText(`Signed in as ${email}`)).toBeVisible();
});
