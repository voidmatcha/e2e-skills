import { expect, test } from "@playwright/test";

const items = (page) => page.getByRole("list", { name: "Articles" }).getByRole("listitem");

test.beforeEach(async ({ page, request }) => {
  await request.post("/api/reset");
  await page.goto("/");
  await expect(items(page)).toHaveCount(10);
});

test("loads ten articles at a time without repeats", async ({ page }) => {
  const more = page.getByRole("button", { name: "Load more" });
  await expect(page.getByText("Showing 10 of 25")).toBeVisible();

  await more.click();
  await expect(page.getByText("Showing 20 of 25")).toBeVisible();
  await expect(more).toBeEnabled();

  await more.click();
  await expect(page.getByText("Showing 25 of 25")).toBeVisible();
  await expect(more).toBeDisabled();

  const titles = await items(page).locator("span").allTextContents();
  expect(titles).toEqual(Array.from({ length: 25 }, (_, i) => `Article ${i + 1}`));
});

test("mark as read toggles and persists across reload", async ({ page }) => {
  await page.getByRole("button", { name: "Mark as read: Article 3", exact: true }).click();
  await expect(page.getByRole("button", { name: "Mark as unread: Article 3", exact: true })).toHaveText("Mark as unread");

  await page.reload();
  await expect(items(page)).toHaveCount(10);
  await expect(page.getByRole("button", { name: "Mark as unread: Article 3", exact: true })).toBeVisible();

  await page.getByRole("button", { name: "Mark as unread: Article 3", exact: true }).click();
  await expect(page.getByRole("button", { name: "Mark as read: Article 3", exact: true })).toHaveText("Mark as read");
  await page.reload();
  await expect(page.getByRole("button", { name: "Mark as read: Article 3", exact: true })).toBeVisible();
});

test("hide read removes read articles and adjusts the count", async ({ page }) => {
  await page.getByRole("button", { name: "Mark as read: Article 1", exact: true }).click();
  await page.getByRole("button", { name: "Mark as read: Article 2", exact: true }).click();
  await expect(page.getByText("Showing 10 of 25")).toBeVisible();

  await page.getByLabel("Hide read").check();
  await expect(items(page)).toHaveCount(8);
  await expect(page.getByText("Article 1", { exact: true })).toHaveCount(0);
  await expect(page.getByText("Article 2", { exact: true })).toHaveCount(0);
  await expect(page.getByText("Showing 8 of 25")).toBeVisible();

  await page.getByLabel("Hide read").uncheck();
  await expect(items(page)).toHaveCount(10);
  await expect(page.getByText("Showing 10 of 25")).toBeVisible();
});
