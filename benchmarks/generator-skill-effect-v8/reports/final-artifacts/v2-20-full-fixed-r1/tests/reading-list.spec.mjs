import { expect, test } from "@playwright/test";

const articleTitles = (start, end) => {
  return Array.from({ length: end - start + 1 }, (_, index) => `Article ${start + index}`);
};

const unreadArticleRows = (start, end) => {
  return articleTitles(start, end).map((title) => `${title}Mark as read`);
};

const articlesList = (page) => page.getByRole("list", { name: "Articles", exact: true });
const articleItems = (page) => articlesList(page).getByRole("listitem");
const countText = (page, shown) => page.getByText(`Showing ${shown} of 25`);
const loadMoreButton = (page) => page.getByRole("button", { name: "Load more", exact: true });
const markAsReadButton = (page, title) => page.getByRole("button", { name: `Mark as read: ${title}`, exact: true });
const markAsUnreadButton = (page, title) => page.getByRole("button", { name: `Mark as unread: ${title}`, exact: true });

test.beforeEach(async ({ page, request }) => {
  const reset = await request.post("/api/reset");
  if (!reset.ok()) {
    throw new Error(`Reset failed with status ${reset.status()}`);
  }
  await page.goto("/");
});

test("loads the first page of articles with the total count", async ({ page }) => {
  await expect(articleItems(page)).toHaveText(unreadArticleRows(1, 10));
  await expect(countText(page, 10)).toBeVisible();
  await expect(loadMoreButton(page)).toBeEnabled();
});

test("loads all articles without repeats and disables loading at the end", async ({ page }) => {
  const loadMore = loadMoreButton(page);

  await loadMore.click();
  await expect(articleItems(page)).toHaveText(unreadArticleRows(1, 20));
  await expect(countText(page, 20)).toBeVisible();

  await loadMore.click();
  await expect(articleItems(page)).toHaveText(unreadArticleRows(1, 25));
  await expect(countText(page, 25)).toBeVisible();
  await expect(loadMore).toBeDisabled();
});

test("persists a read article across reloads and allows marking it unread", async ({ page }) => {
  const readRequest = page.waitForRequest((request) => (
    request.method() === "POST" && request.url().endsWith("/api/articles/1/read")
  ));
  await markAsReadButton(page, "Article 1").click();
  await readRequest;
  await expect(markAsUnreadButton(page, "Article 1")).toBeVisible();

  await page.reload();
  await expect(markAsUnreadButton(page, "Article 1")).toBeVisible();

  const unreadRequest = page.waitForRequest((request) => (
    request.method() === "POST" && request.url().endsWith("/api/articles/1/unread")
  ));
  await markAsUnreadButton(page, "Article 1").click();
  await unreadRequest;
  await expect(markAsReadButton(page, "Article 1")).toBeVisible();

  await page.reload();
  await expect(markAsReadButton(page, "Article 1")).toBeVisible();
});

test("hides read articles and updates the shown count", async ({ page }) => {
  const readRequest = page.waitForRequest((request) => (
    request.method() === "POST" && request.url().endsWith("/api/articles/1/read")
  ));
  await markAsReadButton(page, "Article 1").click();
  await readRequest;
  await expect(markAsUnreadButton(page, "Article 1")).toBeVisible();

  await page.getByRole("checkbox", { name: "Hide read", exact: true }).check();

  await expect(articleItems(page)).toHaveText(unreadArticleRows(2, 10));
  await expect(countText(page, 9)).toBeVisible();
});
