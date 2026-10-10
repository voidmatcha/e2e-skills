import { expect, test } from "@playwright/test";

const codeForLastEmail = async (request, email) => {
  const response = await request.get("/api/dev/last-code");
  await expect(response).toBeOK();
  const body = await response.json();
  expect(body.email).toBe(email);
  return body.code;
};

const differentCode = (code) => (code === "000000" ? "111111" : "000000");

test.beforeEach(async ({ request }) => {
  const response = await request.post("/api/reset");
  await expect(response).toBeOK();
});

test("signs in with a code, persists after reload, and signs out", async ({ page, request }) => {
  const email = "visitor@example.test";

  await page.goto("/");
  await page.getByLabel("Email").fill(email);
  await page.getByRole("button", { name: "Send code", exact: true }).click();

  await expect(page.getByRole("status")).toHaveText(`We sent a code to ${email}`);

  const code = await codeForLastEmail(request, email);
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
  const email = "wrong-code@example.test";

  await page.goto("/");
  await page.getByLabel("Email").fill(email);
  await page.getByRole("button", { name: "Send code", exact: true }).click();

  const issuedCode = await codeForLastEmail(request, email);
  await page.getByLabel("Code").fill(differentCode(issuedCode));
  await page.getByRole("button", { name: "Sign in", exact: true }).click();

  await expect(page.getByRole("alert")).toHaveText("That code is not right");
});

test("locks a code after three wrong attempts and accepts a fresh code", async ({ page, request }) => {
  const email = "locked-code@example.test";

  await page.goto("/");
  await page.getByLabel("Email").fill(email);
  await page.getByRole("button", { name: "Send code", exact: true }).click();
  await expect(page.getByRole("status")).toHaveText(`We sent a code to ${email}`);

  const lockedCode = await codeForLastEmail(request, email);
  const wrongCode = differentCode(lockedCode);

  for (let attempt = 0; attempt < 2; attempt += 1) {
    await page.getByLabel("Code").fill(wrongCode);
    await page.getByRole("button", { name: "Sign in", exact: true }).click();
    await expect(page.getByRole("alert")).toHaveText("That code is not right");
  }

  await page.getByLabel("Code").fill(wrongCode);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.getByRole("alert")).toHaveText("Too many attempts. Request a new code.");

  await page.getByLabel("Code").fill(lockedCode);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.getByRole("alert")).toHaveText("Too many attempts. Request a new code.");

  await page.getByRole("button", { name: "Request a new code", exact: true }).click();
  await expect(page.getByRole("status")).toHaveText(`We sent a code to ${email}`);

  const freshCode = await codeForLastEmail(request, email);
  await page.getByLabel("Code").fill(freshCode);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();

  await expect(page.getByText(`Signed in as ${email}`)).toBeVisible();
});
