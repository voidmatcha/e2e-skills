import { expect, test } from "@playwright/test";

async function requestCode(page, email) {
  await page.goto("/");
  await page.getByLabel("Email").fill(email);
  const codeRequest = page.waitForRequest(
    (request) =>
      request.url().endsWith("/api/codes") && request.method() === "POST",
  );
  const codeResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/codes") &&
      response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Send code", exact: true }).click();
  expect((await codeRequest).postDataJSON()).toEqual({ email });
  expect((await codeResponse).status()).toBe(201);
  await expect(page.getByRole("status")).toHaveText(`We sent a code to ${email}`);
}

async function submitCode(page, email, code) {
  await page.getByLabel("Code").fill(code);
  const sessionRequest = page.waitForRequest(
    (request) =>
      request.url().endsWith("/api/session") && request.method() === "POST",
  );
  const sessionResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/session") &&
      response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  expect((await sessionRequest).postDataJSON()).toEqual({ email, code });
  return sessionResponse;
}

async function lastIssuedCode(request) {
  const response = await request.get("/api/dev/last-code");
  expect(response.ok()).toBe(true);
  const body = await response.json();
  return body.code;
}

test("signs in with an emailed code and can sign out", async ({ page, request }) => {
  const email = "signed-in@example.test";

  await requestCode(page, email);
  expect((await submitCode(page, email, await lastIssuedCode(request))).status()).toBe(
    201,
  );

  await expect(page.getByText(`Signed in as ${email}`)).toBeVisible();

  await page.reload();
  await expect(page.getByText(`Signed in as ${email}`)).toBeVisible();

  const signOutResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/session") &&
      response.request().method() === "DELETE",
  );
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  expect((await signOutResponse).status()).toBe(200);
  await expect(
    page.getByRole("textbox", { name: "Email", exact: true }),
  ).toBeVisible();
});

test("shows wrong-code errors and accepts a new code after lockout", async ({
  page,
  request,
}) => {
  const email = "lockout@example.test";

  await requestCode(page, email);
  const lockedCode = await lastIssuedCode(request);

  expect((await submitCode(page, email, "000000")).status()).toBe(401);
  await expect(page.getByRole("alert")).toHaveText("That code is not right");

  expect((await submitCode(page, email, "111111")).status()).toBe(401);
  expect((await submitCode(page, email, "222222")).status()).toBe(423);
  expect((await submitCode(page, email, lockedCode)).status()).toBe(423);
  await expect(page.getByRole("alert")).toHaveText(
    "Too many attempts. Request a new code.",
  );

  await page
    .getByRole("button", { name: "Request a new code", exact: true })
    .click();
  await expect(page.getByRole("status")).toHaveText(`We sent a code to ${email}`);
  const freshCode = await lastIssuedCode(request);
  expect(freshCode).not.toBe(lockedCode);
  expect((await submitCode(page, email, freshCode)).status()).toBe(201);

  await expect(page.getByText(`Signed in as ${email}`)).toBeVisible();
});
