import { expect, test } from "@playwright/test";

// Deliberately shallow: happy path and visibility only. It exists to measure headroom, never to be shown to a model.
test.beforeEach(async ({ page }) => {
  await page.request.post("/api/reset");
  await page.goto("/");
});

test("adds a note", async ({ page }) => {
  await page.fill("#nt-title", "Groceries");
  await page.click("button[type=submit]");
  await expect(page.getByText("Groceries")).toBeVisible();
});

test("edits a note", async ({ page }) => {
  await page.fill("#nt-title", "Draft");
  await page.click("button[type=submit]");
  await page.click("#nt-list li:nth-child(1) button:nth-of-type(1)");
  await page.fill("#nt-list li:nth-child(1) input", "Final");
  await page.click("#nt-list li:nth-child(1) button");
  await expect(page.getByText("Final")).toBeVisible();
});

test("deletes a note", async ({ page }) => {
  await page.fill("#nt-title", "Gone");
  await page.click("button[type=submit]");
  await page.click("#nt-list li:nth-child(1) button:nth-of-type(2)");
  await expect(page.getByText("Gone")).not.toBeVisible();
});
