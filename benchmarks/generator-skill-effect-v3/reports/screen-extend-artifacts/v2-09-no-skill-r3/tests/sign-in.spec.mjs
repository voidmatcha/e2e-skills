import { expect, test } from "@playwright/test";

const email = "visitor@example.com";

test.beforeEach(async ({ page, request }) => {
  await request.post("/api/reset");
  await page.goto("/");
});

async function requestCode(page, request) {
  await page.getByLabel("Email").fill(email);
  await page.getByRole("button", { name: "Send code" }).click();
  await expect(page.getByRole("status")).toHaveText(`We sent a code to ${email}`);
  const issued = await (await request.get("/api/dev/last-code")).json();
  expect(issued.email).toBe(email);
  return issued.code;
}

const wrongCodeFor = (code) => (code === "000000" ? "000001" : "000000");

async function enterCode(page, code) {
  await page.getByLabel("Code").fill(code);
  await page.getByRole("button", { name: "Sign in" }).click();
}

test("signs in with the issued code, persists across reload, and signs out", async ({ page, request }) => {
  const code = await requestCode(page, request);
  await enterCode(page, code);
  await expect(page.getByText(`Signed in as ${email}`)).toBeVisible();

  await page.reload();
  await expect(page.getByText(`Signed in as ${email}`)).toBeVisible();

  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page.getByLabel("Email")).toBeVisible();
  await expect(page.getByText("Signed in as")).toBeHidden();

  await page.reload();
  await expect(page.getByLabel("Email")).toBeVisible();
});

test("a wrong code shows an error and does not sign in", async ({ page, request }) => {
  const code = await requestCode(page, request);
  await enterCode(page, wrongCodeFor(code));
  await expect(page.getByRole("alert")).toHaveText("That code is not right");
  await expect(page.getByText("Signed in as")).toBeHidden();
});

test("three wrong codes lock the code, and a new code resets the attempts", async ({ page, request }) => {
  const code = await requestCode(page, request);
  const wrong = wrongCodeFor(code);

  for (let i = 0; i < 2; i++) {
    await enterCode(page, wrong);
    await expect(page.getByRole("alert")).toHaveText("That code is not right");
  }
  await enterCode(page, wrong);
  await expect(page.getByRole("alert")).toHaveText("Too many attempts. Request a new code.");

  // Even the right code is now refused.
  await enterCode(page, code);
  await expect(page.getByRole("alert")).toHaveText("Too many attempts. Request a new code.");
  await expect(page.getByText("Signed in as")).toBeHidden();

  await page.getByRole("button", { name: "Request a new code" }).click();
  await expect(page.getByRole("alert")).toBeEmpty();
  const fresh = (await (await request.get("/api/dev/last-code")).json()).code;

  // Attempt count starts over: two wrong codes are still "not right", not locked.
  const wrongFresh = wrongCodeFor(fresh);
  for (let i = 0; i < 2; i++) {
    await enterCode(page, wrongFresh);
    await expect(page.getByRole("alert")).toHaveText("That code is not right");
  }

  await enterCode(page, fresh);
  await expect(page.getByText(`Signed in as ${email}`)).toBeVisible();
});
