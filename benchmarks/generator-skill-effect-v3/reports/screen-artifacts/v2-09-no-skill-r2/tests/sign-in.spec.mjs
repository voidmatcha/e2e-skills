import { expect, test } from "@playwright/test";

const EMAIL = "visitor@example.com";

test.beforeEach(async ({ page, request }) => {
  await request.post("/api/reset");
  await page.goto("/");
});

async function requestCode(page, request) {
  await page.getByLabel("Email").fill(EMAIL);
  await page.getByRole("button", { name: "Send code" }).click();
  await expect(page.getByText(`We sent a code to ${EMAIL}`)).toBeVisible();
  const { email, code } = await (await request.get("/api/dev/last-code")).json();
  expect(email).toBe(EMAIL);
  return code;
}

const wrongCodeFor = (code) => (code === "000000" ? "111111" : "000000");

async function submitCode(page, code) {
  await page.getByLabel("Code").fill(code);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
}

test("signs in with the issued code, stays signed in on reload, and signs out", async ({ page, request }) => {
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

test("a wrong code is rejected and the right code still works afterwards", async ({ page, request }) => {
  const code = await requestCode(page, request);
  await submitCode(page, wrongCodeFor(code));
  await expect(page.getByRole("alert")).toHaveText("That code is not right");
  await expect(page.getByText("Signed in as")).toBeHidden();

  await submitCode(page, code);
  await expect(page.getByText(`Signed in as ${EMAIL}`)).toBeVisible();
});

test("three wrong codes lock the code, and a new code starts the count over", async ({ page, request }) => {
  const code = await requestCode(page, request);
  const wrong = wrongCodeFor(code);

  await submitCode(page, wrong);
  await expect(page.getByRole("alert")).toHaveText("That code is not right");
  await submitCode(page, wrong);
  await expect(page.getByRole("alert")).toHaveText("That code is not right");
  await submitCode(page, wrong);
  await expect(page.getByRole("alert")).toHaveText("Too many attempts. Request a new code.");

  // Even the right code is refused now.
  await submitCode(page, code);
  await expect(page.getByRole("alert")).toHaveText("Too many attempts. Request a new code.");
  await expect(page.getByText("Signed in as")).toBeHidden();

  await page.getByRole("button", { name: "Request a new code" }).click();
  const { code: fresh } = await (await request.get("/api/dev/last-code")).json();
  await expect(page.getByRole("alert")).toHaveText("");

  // Attempt count restarted: two wrong codes do not lock the fresh code.
  const wrongFresh = wrongCodeFor(fresh);
  await submitCode(page, wrongFresh);
  await expect(page.getByRole("alert")).toHaveText("That code is not right");
  await submitCode(page, wrongFresh);
  await expect(page.getByRole("alert")).toHaveText("That code is not right");

  await submitCode(page, fresh);
  await expect(page.getByText(`Signed in as ${EMAIL}`)).toBeVisible();
});
