import { expect, test } from "@playwright/test";

const email = "person@example.com";

test.beforeEach(async ({ request }) => {
  await request.post("/api/reset");
});

async function requestCode(page, address = email) {
  await page.goto("/");
  await page.getByLabel("Email").fill(address);
  await page.getByRole("button", { name: "Send code" }).click();
  await expect(page.getByText(`We sent a code to ${address}`)).toBeVisible();
}

async function lastCode(request) {
  const response = await request.get("/api/dev/last-code");
  expect(response.ok()).toBeTruthy();
  return response.json();
}

async function submitCode(page, code) {
  await page.getByLabel("Code").fill(code);
  await page.getByRole("button", { name: "Sign in" }).click();
}

test("signs in with an emailed code, persists across reload, and signs out", async ({ page, request }) => {
  await requestCode(page);
  const issued = await lastCode(request);

  await submitCode(page, issued.code);
  await expect(page.getByText(`Signed in as ${email}`)).toBeVisible();

  await page.reload();
  await expect(page.getByText(`Signed in as ${email}`)).toBeVisible();

  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
  await expect(page.getByLabel("Email")).toBeVisible();
});

test("shows an error for a wrong code", async ({ page }) => {
  await requestCode(page);

  await submitCode(page, "000000");

  await expect(page.getByRole("alert")).toHaveText("That code is not right");
});

test("locks a code after three wrong attempts, then accepts a fresh code", async ({ page, request }) => {
  await requestCode(page);
  const issued = await lastCode(request);

  await submitCode(page, wrongCodeFor(issued.code));
  await expect(page.getByRole("alert")).toHaveText("That code is not right");

  await submitCode(page, wrongCodeFor(issued.code));
  await expect(page.getByRole("alert")).toHaveText("That code is not right");

  await submitCode(page, wrongCodeFor(issued.code));
  await expect(page.getByRole("alert")).toHaveText("Too many attempts. Request a new code.");

  await submitCode(page, issued.code);
  await expect(page.getByRole("alert")).toHaveText("Too many attempts. Request a new code.");

  await page.getByRole("button", { name: "Request a new code" }).click();
  const fresh = await lastCode(request);

  await submitCode(page, fresh.code);
  await expect(page.getByText(`Signed in as ${email}`)).toBeVisible();
});

function wrongCodeFor(code) {
  return code === "000000" ? "111111" : "000000";
}
