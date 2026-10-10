import { expect, test } from "@playwright/test";

const articleTitle = (number) => `Article ${number}`;
const readButtonName = (number) => `Mark as read: ${articleTitle(number)}`;
const unreadButtonName = (number) => `Mark as unread: ${articleTitle(number)}`;

test.beforeEach(async ({ page }) => {
  await page.request.post("/api/reset");
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Reading list", exact: true })).toBeVisible();
});

test("loads all articles ten at a time without repeats", async ({ page }) => {
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

  const renderedArticles = await articles.allTextContents();
  expect(new Set(renderedArticles).size).toBe(25);
  for (let number = 1; number <= 25; number += 1) {
    expect(renderedArticles.some((text) => text.includes(articleTitle(number)))).toBe(true);
  }
  await expect(loadMore).toBeDisabled();
});

test("stores read state on the server and restores it after reload", async ({ page }) => {
  const readRequest = page.waitForRequest((request) =>
    request.method() === "POST" && request.url().endsWith("/api/articles/1/read")
  );
  await page.getByRole("button", { name: readButtonName(1), exact: true }).click();
  await readRequest;

  await expect(page.getByRole("button", { name: unreadButtonName(1), exact: true })).toBeVisible();

  await page.reload();
  await expect(page.getByRole("button", { name: unreadButtonName(1), exact: true })).toBeVisible();

  const unreadRequest = page.waitForRequest((request) =>
    request.method() === "POST" && request.url().endsWith("/api/articles/1/unread")
  );
  await page.getByRole("button", { name: unreadButtonName(1), exact: true }).click();
  await unreadRequest;
  await expect(page.getByRole("button", { name: readButtonName(1), exact: true })).toBeVisible();
});

test("hides read articles from the list and visible count", async ({ page }) => {
  for (const number of [1, 2]) {
    const readRequest = page.waitForRequest((request) =>
      request.method() === "POST" && request.url().endsWith(`/api/articles/${number}/read`)
    );
    await page.getByRole("button", { name: readButtonName(number), exact: true }).click();
    await readRequest;
    await expect(page.getByRole("button", { name: unreadButtonName(number), exact: true })).toBeVisible();
  }

  await page.getByRole("checkbox", { name: "Hide read", exact: true }).check();

  await expect(page.getByText("Showing 8 of 25")).toBeVisible();
  await expect(page.getByRole("button", { name: unreadButtonName(1), exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: unreadButtonName(2), exact: true })).toHaveCount(0);
  await expect(page.getByText(articleTitle(3), { exact: true })).toBeVisible();
});
