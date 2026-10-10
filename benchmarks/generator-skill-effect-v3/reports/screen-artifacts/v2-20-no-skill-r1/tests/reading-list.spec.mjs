import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page, request }) => {
  await request.post("/api/reset");
  await page.goto("/");
});

const items = (page) => page.getByRole("list", { name: "Articles" }).getByRole("listitem");
const loadMore = (page) => page.getByRole("button", { name: "Load more" });
const titles = (n, from = 1) => Array.from({ length: n }, (_, i) => `Article ${from + i}`);
const row = (page, title) => items(page).filter({ has: page.getByText(title, { exact: true }) });

test("loads the first ten articles", async ({ page }) => {
  await expect(items(page)).toHaveCount(10);
  await expect(page.getByText("Showing 10 of 25")).toBeVisible();
  await expect(loadMore(page)).toBeEnabled();
});

test("Load more pages through all 25 articles without repeats", async ({ page }) => {
  await loadMore(page).click();
  await expect(items(page)).toHaveCount(20);
  await expect(page.getByText("Showing 20 of 25")).toBeVisible();
  await loadMore(page).click();
  await expect(items(page)).toHaveCount(25);
  await expect(page.getByText("Showing 25 of 25")).toBeVisible();
  await expect(loadMore(page)).toBeDisabled();

  const spans = items(page).locator("span");
  await expect(spans).toHaveText(titles(25));
});

test("Mark as read toggles and the state survives a reload", async ({ page }) => {
  const article = row(page, "Article 3");
  await article.getByRole("button", { name: "Mark as read" }).click();
  await expect(article.getByRole("button", { name: "Mark as unread" })).toBeVisible();
  await expect(row(page, "Article 4").getByRole("button", { name: "Mark as read" })).toBeVisible();

  await page.reload();
  await expect(row(page, "Article 3").getByRole("button", { name: "Mark as unread" })).toBeVisible();

  await row(page, "Article 3").getByRole("button", { name: "Mark as unread" }).click();
  await expect(row(page, "Article 3").getByRole("button", { name: "Mark as read" })).toBeVisible();
  await page.reload();
  await expect(row(page, "Article 3").getByRole("button", { name: "Mark as read" })).toBeVisible();
});

test("Hide read removes read articles from the list and the count", async ({ page }) => {
  for (const n of [1, 2]) {
    await row(page, `Article ${n}`).getByRole("button", { name: "Mark as read" }).click();
    await expect(row(page, `Article ${n}`).getByRole("button", { name: "Mark as unread" })).toBeVisible();
  }
  await page.getByLabel("Hide read").check();
  await expect(items(page)).toHaveCount(8);
  await expect(items(page).locator("span")).toHaveText(titles(8, 3));
  await expect(page.getByText("Showing 8 of 25")).toBeVisible();

  await page.getByLabel("Hide read").uncheck();
  await expect(items(page)).toHaveCount(10);
  await expect(page.getByText("Showing 10 of 25")).toBeVisible();
});

test("Hide read still applies after Load more", async ({ page }) => {
  await row(page, "Article 1").getByRole("button", { name: "Mark as read" }).click();
  await page.getByLabel("Hide read").check();
  await expect(page.getByText("Showing 9 of 25")).toBeVisible();
  await loadMore(page).click();
  await expect(page.getByText("Showing 19 of 25")).toBeVisible();
  await expect(row(page, "Article 1")).toHaveCount(0);
});
