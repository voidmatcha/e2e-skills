import { expect, test } from "@playwright/test";

const articleTitles = async (page) => page.getByRole("list", { name: "Articles" }).locator("li span").allTextContents();

test.beforeEach(async ({ request }) => {
  await request.post("/api/reset");
});

test("loads all articles in order without duplicates", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByText("Showing 10 of 25")).toBeVisible();
  await expect(page.getByRole("button", { name: "Load more" })).toBeEnabled();
  await expect(page.getByRole("listitem")).toHaveCount(10);
  expect(await articleTitles(page)).toEqual(Array.from({ length: 10 }, (_, index) => `Article ${index + 1}`));

  await page.getByRole("button", { name: "Load more" }).click();
  await expect(page.getByText("Showing 20 of 25")).toBeVisible();
  await expect(page.getByRole("listitem")).toHaveCount(20);

  await page.getByRole("button", { name: "Load more" }).click();
  await expect(page.getByText("Showing 25 of 25")).toBeVisible();
  await expect(page.getByRole("listitem")).toHaveCount(25);
  await expect(page.getByRole("button", { name: "Load more" })).toBeDisabled();

  const titles = await articleTitles(page);
  expect(titles).toEqual(Array.from({ length: 25 }, (_, index) => `Article ${index + 1}`));
  expect(new Set(titles).size).toBe(25);
});

test("persists read state and hides read articles from the visible count", async ({ page }) => {
  await page.goto("/");

  await page.getByRole("button", { name: "Mark as read: Article 1", exact: true }).click();
  await expect(page.getByRole("button", { name: "Mark as unread: Article 1", exact: true })).toBeVisible();

  await page.reload();
  await expect(page.getByRole("button", { name: "Mark as unread: Article 1", exact: true })).toBeVisible();

  await page.getByRole("checkbox", { name: "Hide read" }).check();
  await expect(page.getByText("Showing 9 of 25")).toBeVisible();
  await expect(page.getByText("Article 1", { exact: true })).toBeHidden();
  await expect(page.getByRole("listitem")).toHaveCount(9);

  await page.getByRole("checkbox", { name: "Hide read" }).uncheck();
  await page.getByRole("button", { name: "Mark as unread: Article 1", exact: true }).click();
  await expect(page.getByRole("button", { name: "Mark as read: Article 1", exact: true })).toBeVisible();

  await page.getByRole("checkbox", { name: "Hide read" }).check();
  await expect(page.getByText("Showing 10 of 25")).toBeVisible();
  await expect(page.getByText("Article 1", { exact: true })).toBeVisible();
});
