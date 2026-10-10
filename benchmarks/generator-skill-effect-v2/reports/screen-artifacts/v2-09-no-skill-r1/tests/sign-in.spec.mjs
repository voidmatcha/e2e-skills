import { expect, test } from "@playwright/test";

const email = "visitor@example.com";

test.beforeEach(async ({ page, request }) => {
  await request.post("/api/reset");
  await page.goto("/");
});

async function requestCode(page) {
  await page.getByLabel("Email").fill(email);
  await page.getByRole("button", { name: "Send code" }).click();
  await expect(page.getByText(`We sent a code to ${email}`)).toBeVisible();
}

async function issuedCode(request) {
  const res = await request.get("/api/dev/last-code");
  const body = await res.json();
  expect(body.email).toBe(email);
  return body.code;
}

async function submitCode(page, code) {
  await page.getByLabel("Code").fill(code);
  await page.getByRole("button", { name: "Sign in" }).click();
}

function wrongCode(code) {
  return code === "000000" ? "111111" : "000000";
}

test("signs in with the issued code", async ({ page, request }) => {
  await requestCode(page);
  await submitCode(page, await issuedCode(request));
  await expect(page.getByText(`Signed in as ${email}`)).toBeVisible();
});

test("stays signed in across a reload", async ({ page, request }) => {
  await requestCode(page);
  await submitCode(page, await issuedCode(request));
  await expect(page.getByText(`Signed in as ${email}`)).toBeVisible();
  await page.reload();
  await expect(page.getByText(`Signed in as ${email}`)).toBeVisible();
});

test("sign out returns to the email step", async ({ page, request }) => {
  await requestCode(page);
  await submitCode(page, await issuedCode(request));
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page.getByLabel("Email")).toBeVisible();
  await expect(page.getByRole("button", { name: "Send code" })).toBeVisible();
  await page.reload();
  await expect(page.getByLabel("Email")).toBeVisible();
  await expect(page.getByText("Signed in as")).toHaveCount(0);
});

test("a wrong code is rejected", async ({ page, request }) => {
  await requestCode(page);
  const code = await issuedCode(request);
  await submitCode(page, wrongCode(code));
  await expect(page.getByRole("alert")).toHaveText("That code is not right");
  await expect(page.getByText("Signed in as")).toHaveCount(0);
});

test("three wrong codes lock the code, even the right one", async ({ page, request }) => {
  await requestCode(page);
  const code = await issuedCode(request);
  const bad = wrongCode(code);
  await submitCode(page, bad);
  await expect(page.getByRole("alert")).toHaveText("That code is not right");
  await submitCode(page, bad);
  await expect(page.getByRole("alert")).toHaveText("That code is not right");
  await submitCode(page, bad);
  await expect(page.getByRole("alert")).toHaveText("Too many attempts. Request a new code.");

  await submitCode(page, code);
  await expect(page.getByRole("alert")).toHaveText("Too many attempts. Request a new code.");
  await expect(page.getByText("Signed in as")).toHaveCount(0);
});

test("requesting a new code after lockout works and resets the attempt count", async ({ page, request }) => {
  await requestCode(page);
  const oldCode = await issuedCode(request);
  const bad = wrongCode(oldCode);
  for (let i = 0; i < 3; i++) await submitCode(page, bad);
  await expect(page.getByRole("alert")).toHaveText("Too many attempts. Request a new code.");

  await page.getByRole("button", { name: "Request a new code" }).click();
  await expect(page.getByRole("alert")).toHaveText("");
  const newCode = await issuedCode(request);

  // Attempt count starts over: two wrong codes are not yet a lockout.
  const bad2 = wrongCode(newCode);
  await submitCode(page, bad2);
  await expect(page.getByRole("alert")).toHaveText("That code is not right");
  await submitCode(page, bad2);
  await expect(page.getByRole("alert")).toHaveText("That code is not right");

  await submitCode(page, newCode);
  await expect(page.getByText(`Signed in as ${email}`)).toBeVisible();
});
