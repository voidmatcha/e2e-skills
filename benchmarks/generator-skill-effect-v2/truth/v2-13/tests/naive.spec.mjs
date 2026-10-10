import { expect, test } from "@playwright/test";

// Deliberately shallow: happy path and visibility only. It exists as a sanity floor, never to be shown to a model.
test.beforeEach(async ({ page }) => {
  await page.request.post("/api/reset");
  await page.goto("/");
});

test("moves a card to done", async ({ page }) => {
  await page.selectOption("section[data-column='Todo'] li:nth-child(1) select", "Done");
  await expect(page.locator("section[data-column='Done']")).toContainText("Write spec");
});

test("shows the limit message", async ({ page }) => {
  await page.getByLabel("Move Write spec").selectOption("In progress");
  await page.getByLabel("Move Design logo").selectOption("In progress");
  await expect(page.locator("#kb-message")).toContainText("full");
});
