import { expect, test } from "@playwright/test";

test.beforeEach(async ({ request }) => {
  await request.post("/api/reset");
});

const articles = (page) => page.getByRole("list", { name: "Articles" }).getByRole("listitem");

async function articleTitles(page) {
  return articles(page).locator("span").allTextContents();
}

test("loads all articles ten at a time without repeating any", async ({ page }) => {
  await page.goto("/");

  await expect(articles(page)).toHaveCount(10);
  await expect(page.getByText("Showing 10 of 25")).toBeVisible();

  let titles = await articleTitles(page);
  expect(titles).toEqual(Array.from({ length: 10 }, (_, i) => `Article ${i + 1}`));

  await page.getByRole("button", { name: "Load more" }).click();
  await expect(articles(page)).toHaveCount(20);
  await expect(page.getByText("Showing 20 of 25")).toBeVisible();

  await page.getByRole("button", { name: "Load more" }).click();
  await expect(articles(page)).toHaveCount(25);
  await expect(page.getByText("Showing 25 of 25")).toBeVisible();
  await expect(page.getByRole("button", { name: "Load more" })).toBeDisabled();

  titles = await articleTitles(page);
  expect(titles).toEqual(Array.from({ length: 25 }, (_, i) => `Article ${i + 1}`));
  expect(new Set(titles).size).toBe(25);
});

test("persists read state after a reload", async ({ page }) => {
  await page.goto("/");

  await page.getByRole("button", { name: "Mark as read: Article 1", exact: true }).click();
  await expect(page.getByRole("button", { name: "Mark as unread: Article 1", exact: true })).toBeVisible();

  await page.reload();

  await expect(page.getByRole("button", { name: "Mark as unread: Article 1", exact: true })).toBeVisible();
  await expect(page.getByText("Showing 10 of 25")).toBeVisible();

  await page.getByRole("button", { name: "Mark as unread: Article 1", exact: true }).click();
  await expect(page.getByRole("button", { name: "Mark as read: Article 1", exact: true })).toBeVisible();
});

test("hides read articles from the list and count", async ({ page }) => {
  await page.goto("/");

  await page.getByRole("button", { name: "Mark as read: Article 1", exact: true }).click();
  await page.getByRole("button", { name: "Mark as read: Article 2", exact: true }).click();
  await page.getByLabel("Hide read").check();

  await expect(articles(page)).toHaveCount(8);
  await expect(page.getByText("Showing 8 of 25")).toBeVisible();
  await expect(page.getByText("Article 1", { exact: true })).toBeHidden();
  await expect(page.getByText("Article 2", { exact: true })).toBeHidden();
  await expect(page.getByText("Article 3", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: "Load more" }).click();

  await expect(articles(page)).toHaveCount(18);
  await expect(page.getByText("Showing 18 of 25")).toBeVisible();
  await expect(page.getByText("Article 1", { exact: true })).toBeHidden();
  await expect(page.getByText("Article 20", { exact: true })).toBeVisible();
});
