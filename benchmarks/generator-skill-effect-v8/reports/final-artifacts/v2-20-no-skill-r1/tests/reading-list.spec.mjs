import { expect, test } from "@playwright/test";

test.beforeEach(async ({ request }) => {
  await request.post("/api/reset");
});

const articles = (page) => page.getByRole("list", { name: "Articles" }).getByRole("listitem");

const article = (page, title) =>
  articles(page).filter({ has: page.getByText(title, { exact: true }) });

const articleTitles = async (page) =>
  await articles(page).locator("span").evaluateAll((items) => items.map((item) => item.textContent));

test("loads all articles ten at a time without repeats", async ({ page }) => {
  await page.goto("/");

  await expect(articles(page)).toHaveCount(10);
  await expect(page.getByText("Showing 10 of 25")).toBeVisible();
  await expect(page.getByRole("button", { name: "Load more" })).toBeEnabled();
  expect(await articleTitles(page)).toEqual(Array.from({ length: 10 }, (_, i) => `Article ${i + 1}`));

  await page.getByRole("button", { name: "Load more" }).click();

  await expect(articles(page)).toHaveCount(20);
  await expect(page.getByText("Showing 20 of 25")).toBeVisible();
  expect(new Set(await articleTitles(page)).size).toBe(20);

  await page.getByRole("button", { name: "Load more" }).click();

  await expect(articles(page)).toHaveCount(25);
  await expect(page.getByText("Showing 25 of 25")).toBeVisible();
  await expect(page.getByRole("button", { name: "Load more" })).toBeDisabled();
  expect(await articleTitles(page)).toEqual(Array.from({ length: 25 }, (_, i) => `Article ${i + 1}`));
});

test("persists read state after reload and can mark unread again", async ({ page }) => {
  await page.goto("/");

  await article(page, "Article 1").getByRole("button", { name: "Mark as read: Article 1" }).click();
  await expect(article(page, "Article 1").getByRole("button", { name: "Mark as unread: Article 1" })).toBeVisible();

  await page.reload();

  await expect(article(page, "Article 1").getByRole("button", { name: "Mark as unread: Article 1" })).toBeVisible();

  await article(page, "Article 1").getByRole("button", { name: "Mark as unread: Article 1" }).click();
  await expect(article(page, "Article 1").getByRole("button", { name: "Mark as read: Article 1" })).toBeVisible();

  await page.reload();

  await expect(article(page, "Article 1").getByRole("button", { name: "Mark as read: Article 1" })).toBeVisible();
});

test("hides read articles and removes them from the visible count", async ({ page }) => {
  await page.goto("/");

  await article(page, "Article 1").getByRole("button", { name: "Mark as read: Article 1" }).click();
  await article(page, "Article 2").getByRole("button", { name: "Mark as read: Article 2" }).click();

  await page.getByLabel("Hide read").check();

  await expect(articles(page)).toHaveCount(8);
  await expect(page.getByText("Showing 8 of 25")).toBeVisible();
  await expect(page.getByText("Article 1", { exact: true })).toBeHidden();
  await expect(page.getByText("Article 2", { exact: true })).toBeHidden();
  await expect(page.getByText("Article 3", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: "Load more" }).click();

  await expect(articles(page)).toHaveCount(18);
  await expect(page.getByText("Showing 18 of 25")).toBeVisible();
  expect(await articleTitles(page)).toEqual([
    ...Array.from({ length: 8 }, (_, i) => `Article ${i + 3}`),
    ...Array.from({ length: 10 }, (_, i) => `Article ${i + 11}`),
  ]);

  await page.getByLabel("Hide read").uncheck();

  await expect(articles(page)).toHaveCount(20);
  await expect(page.getByText("Showing 20 of 25")).toBeVisible();
  await expect(article(page, "Article 1").getByRole("button", { name: "Mark as unread: Article 1" })).toBeVisible();
  await expect(article(page, "Article 2").getByRole("button", { name: "Mark as unread: Article 2" })).toBeVisible();
});
