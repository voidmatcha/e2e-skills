import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page, request }) => {
  await request.post("/api/reset");
  await page.goto("/");
});

test("loads all articles without repeats and disables loading at the end", async ({ page }) => {
  const articles = page.getByRole("list", { name: "Articles", exact: true }).getByRole("listitem");
  const loadMore = page.getByRole("button", { name: "Load more", exact: true });

  await expect(articles).toHaveCount(10);
  await expect(page.getByText("Showing 10 of 25")).toBeVisible();

  await loadMore.click();
  await expect(articles).toHaveCount(20);
  await expect(page.getByText("Showing 20 of 25")).toBeVisible();

  await loadMore.click();
  await expect(articles).toHaveCount(25);
  await expect(page.getByText("Showing 25 of 25")).toBeVisible();
  await expect(loadMore).toBeDisabled();

  const articleTitles = (await articles.allTextContents()).map((text) => text.match(/Article \d+/)?.[0]);
  expect(articleTitles).toEqual(Array.from({ length: 25 }, (_, index) => `Article ${index + 1}`));
  expect(new Set(articleTitles).size).toBe(25);
});

test("persists read state after reload", async ({ page }) => {
  const markAsRead = page.getByRole("button", { name: "Mark as read: Article 3", exact: true });
  const readRequest = page.waitForRequest((request) => request.method() === "POST" && request.url().endsWith("/api/articles/3/read"));

  await markAsRead.click();
  await readRequest;
  await expect(page.getByRole("button", { name: "Mark as unread: Article 3", exact: true })).toBeVisible();

  await page.reload();

  await expect(page.getByRole("button", { name: "Mark as unread: Article 3", exact: true })).toBeVisible();
});

test("hides read articles and updates the shown count", async ({ page }) => {
  const articleList = page.getByRole("list", { name: "Articles", exact: true });
  const article2ReadRequest = page.waitForRequest((request) => request.method() === "POST" && request.url().endsWith("/api/articles/2/read"));
  await page.getByRole("button", { name: "Mark as read: Article 2", exact: true }).click();
  await article2ReadRequest;

  const article4ReadRequest = page.waitForRequest((request) => request.method() === "POST" && request.url().endsWith("/api/articles/4/read"));
  await page.getByRole("button", { name: "Mark as read: Article 4", exact: true }).click();
  await article4ReadRequest;

  await page.getByLabel("Hide read").check();

  await expect(page.getByText("Showing 8 of 25")).toBeVisible();
  await expect(articleList).not.toContainText("Article 2");
  await expect(articleList).not.toContainText("Article 4");
  await expect(articleList.getByText("Article 3", { exact: true })).toBeVisible();
});
