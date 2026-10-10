import { expect, test } from "@playwright/test";

const email = "visitor@example.com";

test.beforeEach(async ({ request }) => {
  await request.post("/api/reset");
});

async function lastCode(request) {
  const res = await request.get("/api/dev/last-code");
  return (await res.json()).code;
}

function wrongCodeFor(code) {
  return code === "000000" ? "111111" : "000000";
}

async function requestCode(page) {
  await page.goto("/");
  await page.getByLabel("Email").fill(email);
  await page.getByRole("button", { name: "Send code" }).click();
  await expect(page.getByText(`We sent a code to ${email}`)).toBeVisible();
}

async function submitCode(page, code) {
  await page.getByLabel("Code").fill(code);
  await page.getByRole("button", { name: "Sign in" }).click();
}

test("signs in with the issued code and stays signed in after a reload", async ({ page, request }) => {
  await requestCode(page);
  await submitCode(page, await lastCode(request));
  await expect(page.getByText(`Signed in as ${email}`)).toBeVisible();

  await page.reload();
  await expect(page.getByText(`Signed in as ${email}`)).toBeVisible();
});

test("sign out returns to the email step", async ({ page, request }) => {
  await requestCode(page);
  await submitCode(page, await lastCode(request));
  await expect(page.getByText(`Signed in as ${email}`)).toBeVisible();

  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page.getByLabel("Email")).toBeVisible();
  await expect(page.getByText("Signed in as")).toBeHidden();

  await page.reload();
  await expect(page.getByLabel("Email")).toBeVisible();
});

test("a wrong code shows an error and the right code still works", async ({ page, request }) => {
  await requestCode(page);
  const code = await lastCode(request);
  await submitCode(page, wrongCodeFor(code));
  await expect(page.getByRole("alert")).toHaveText("That code is not right");

  await submitCode(page, code);
  await expect(page.getByText(`Signed in as ${email}`)).toBeVisible();
});

test("three wrong codes lock the code, and a new code starts over", async ({ page, request }) => {
  await requestCode(page);
  const code = await lastCode(request);
  const wrong = wrongCodeFor(code);

  await submitCode(page, wrong);
  await expect(page.getByRole("alert")).toHaveText("That code is not right");
  await submitCode(page, wrong);
  await expect(page.getByRole("alert")).toHaveText("That code is not right");
  await submitCode(page, wrong);
  await expect(page.getByRole("alert")).toHaveText("Too many attempts. Request a new code.");

  // Even the right code is refused once locked.
  await submitCode(page, code);
  await expect(page.getByRole("alert")).toHaveText("Too many attempts. Request a new code.");
  await expect(page.getByText("Signed in as")).toBeHidden();

  await page.getByRole("button", { name: "Request a new code" }).click();
  await expect(page.getByRole("alert")).toHaveText("");
  const fresh = await lastCode(request);
  expect(fresh).not.toBe("");

  // Attempt count starts over: a wrong code is a plain "not right" again.
  await submitCode(page, wrongCodeFor(fresh));
  await expect(page.getByRole("alert")).toHaveText("That code is not right");

  await submitCode(page, fresh);
  await expect(page.getByText(`Signed in as ${email}`)).toBeVisible();
});
