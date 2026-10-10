import { expect, test } from "@playwright/test";

const EMAIL = "visitor@example.com";

test.beforeEach(async ({ page, request }) => {
  await request.post("/api/reset");
  await page.goto("/");
});

async function lastCode(request) {
  const res = await request.get("/api/dev/last-code");
  return (await res.json()).code;
}

function wrongCodeFor(code) {
  return code === "000000" ? "000001" : "000000";
}

async function requestCode(page, request) {
  await page.getByLabel("Email").fill(EMAIL);
  await page.getByRole("button", { name: "Send code" }).click();
  await expect(page.getByText(`We sent a code to ${EMAIL}`)).toBeVisible();
  return lastCode(request);
}

async function submitCode(page, code) {
  await page.getByLabel("Code").fill(code);
  await page.getByRole("button", { name: "Sign in" }).click();
}

test("signs in with the issued code, persists across reload, and signs out", async ({ page, request }) => {
  const code = await requestCode(page, request);
  await submitCode(page, code);
  await expect(page.getByText(`Signed in as ${EMAIL}`)).toBeVisible();

  await page.reload();
  await expect(page.getByText(`Signed in as ${EMAIL}`)).toBeVisible();

  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page.getByLabel("Email")).toBeVisible();
  await expect(page.getByText("Signed in as")).toBeHidden();

  await page.reload();
  await expect(page.getByLabel("Email")).toBeVisible();
});

test("a wrong code shows an error and does not sign in", async ({ page, request }) => {
  const code = await requestCode(page, request);
  await submitCode(page, wrongCodeFor(code));
  await expect(page.getByRole("alert")).toHaveText("That code is not right");
  await expect(page.getByText("Signed in as")).toBeHidden();
});

test("three wrong codes lock the code, even the right one", async ({ page, request }) => {
  const code = await requestCode(page, request);
  const wrong = wrongCodeFor(code);

  for (let i = 0; i < 2; i++) {
    await submitCode(page, wrong);
    await expect(page.getByRole("alert")).toHaveText("That code is not right");
  }
  await submitCode(page, wrong);
  await expect(page.getByRole("alert")).toHaveText("Too many attempts. Request a new code.");

  await submitCode(page, code);
  await expect(page.getByRole("alert")).toHaveText("Too many attempts. Request a new code.");
  await expect(page.getByText("Signed in as")).toBeHidden();
});

test("requesting a new code after lockout issues a working code and resets attempts", async ({ page, request }) => {
  const code = await requestCode(page, request);
  const wrong = wrongCodeFor(code);
  for (let i = 0; i < 3; i++) await submitCode(page, wrong);
  await expect(page.getByRole("alert")).toHaveText("Too many attempts. Request a new code.");

  await page.getByRole("button", { name: "Request a new code" }).click();
  await expect(page.getByRole("alert")).toHaveText("");
  const fresh = await lastCode(request);

  // Attempt count starts over: two wrong codes are not yet a lockout.
  const wrongFresh = wrongCodeFor(fresh);
  for (let i = 0; i < 2; i++) {
    await submitCode(page, wrongFresh);
    await expect(page.getByRole("alert")).toHaveText("That code is not right");
  }

  await submitCode(page, fresh);
  await expect(page.getByText(`Signed in as ${EMAIL}`)).toBeVisible();
});
