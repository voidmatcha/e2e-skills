import { expect, test } from "@playwright/test";

// Deliberately shallow: happy path and visibility only. It exists as a sanity floor, never to be shown to a model.
test.beforeEach(async ({ page }) => {
  await page.request.post("/api/reset");
  await page.goto("/");
});

test("posts and replies", async ({ page }) => {
  await page.fill("#cm-text", "Hello");
  await page.click("#cm-form button");
  await expect(page.getByText("#1 Hello")).toBeVisible();
  await page.click("#cm-thread li button:nth-of-type(1)");
  await page.fill("#cm-text", "Reply");
  await page.click("#cm-form button");
  await expect(page.getByText("#2 Reply")).toBeVisible();
});

test("deletes after confirming", async ({ page }) => {
  await page.fill("#cm-text", "Gone");
  await page.click("#cm-form button");
  page.once("dialog", (dialog) => dialog.accept());
  await page.click("#cm-thread li button:nth-of-type(3)");
  await expect(page.getByText("#1 Gone")).not.toBeVisible();
});
