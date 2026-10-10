import { expect, test } from "@playwright/test";

// Deliberately shallow: happy path and visibility only. It exists as a sanity floor, never to be shown to a model.
test.beforeEach(async ({ page }) => {
  await page.request.post("/api/reset");
  await page.goto("/");
});

test("signs in with a code", async ({ page }) => {
  await page.fill("#pl-email", "ada@example.com");
  await page.click("#pl-email-form button");
  const { code } = await (await page.request.get("/api/dev/last-code")).json();
  await page.fill("#pl-code", code);
  await page.click("#pl-code-form button");
  await expect(page.locator("#pl-whoami")).toContainText("ada@example.com");
});

test("rejects a wrong code", async ({ page }) => {
  await page.fill("#pl-email", "ada@example.com");
  await page.click("#pl-email-form button");
  await page.fill("#pl-code", "999999");
  await page.click("#pl-code-form button");
  await expect(page.locator("#pl-error")).toBeVisible();
});
