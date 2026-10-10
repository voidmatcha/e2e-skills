import { expect, test } from "@playwright/test";

const EMAIL = "ada@example.com";

async function requestCode(page) {
  await page.getByLabel("Email").fill(EMAIL);
  await page.getByRole("button", { name: "Send code" }).click();
  await expect(page.getByRole("status")).toHaveText(`We sent a code to ${EMAIL}`);
  return (await (await page.request.get("/api/dev/last-code")).json()).code;
}

async function enter(page, code) {
  await page.getByLabel("Code").fill(code);
  await page.getByRole("button", { name: "Sign in" }).click();
}

test.beforeEach(async ({ page }) => {
  await page.request.post("/api/reset");
  await page.goto("/");
});

test("signs in with the issued code and stays signed in", async ({ page }) => {
  const code = await requestCode(page);
  await enter(page, code);
  await expect(page.getByText(`Signed in as ${EMAIL}`)).toBeVisible();
  await page.reload();
  await expect(page.getByText(`Signed in as ${EMAIL}`)).toBeVisible();
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page.getByLabel("Email")).toBeVisible();
});

test("a wrong code is rejected with the exact message", async ({ page }) => {
  const code = await requestCode(page);
  await enter(page, code === "000000" ? "000001" : "000000");
  await expect(page.getByRole("alert")).toHaveText("That code is not right");
});

test("three wrong codes lock the code until a new one is requested", async ({ page }) => {
  const code = await requestCode(page);
  const wrong = code === "000000" ? "000001" : "000000";
  for (let i = 0; i < 3; i += 1) {
    await enter(page, wrong);
    await expect(page.getByRole("alert")).toHaveText(/not right|Too many attempts/);
  }
  await enter(page, code);
  await expect(page.getByRole("alert")).toHaveText("Too many attempts. Request a new code.");
  await expect(page.getByText(`Signed in as ${EMAIL}`)).toBeHidden();
  await page.getByRole("button", { name: "Request a new code" }).click();
  await expect(page.getByRole("status")).toHaveText(`We sent a code to ${EMAIL}`);
  const fresh = (await (await page.request.get("/api/dev/last-code")).json()).code;
  await enter(page, fresh);
  await expect(page.getByText(`Signed in as ${EMAIL}`)).toBeVisible();
});
