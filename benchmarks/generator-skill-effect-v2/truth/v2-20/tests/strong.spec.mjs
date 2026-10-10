import { expect, test } from "@playwright/test";

const rows = (page) => page.getByRole("list", { name: "Articles" }).getByRole("listitem");
const more = (page) => page.getByRole("button", { name: "Load more" });
const titles = (from, to) => Array.from({ length: to - from + 1 }, (_, i) => new RegExp(`^Article ${from + i}(?!\\d)`));

test.beforeEach(async ({ page }) => {
  await page.request.post("/api/reset");
  await page.goto("/");
  await expect(rows(page)).toHaveCount(10);
  await expect(page.getByText("Showing 10 of 25")).toBeVisible();
});

test("load more appends without repeating and stops at the end", async ({ page }) => {
  await more(page).click();
  await expect(rows(page)).toHaveText(titles(1, 20));
  await expect(page.getByText("Showing 20 of 25")).toBeVisible();
  await expect(more(page)).toBeEnabled();
  await more(page).click();
  await expect(rows(page)).toHaveText(titles(1, 25));
  await expect(page.getByText("Showing 25 of 25")).toBeVisible();
  await expect(more(page)).toBeDisabled();
});

test("mark as read toggles and persists", async ({ page }) => {
  await page.getByRole("button", { name: "Mark as read: Article 3" }).click();
  await expect(page.getByRole("button", { name: "Mark as unread: Article 3" })).toBeVisible();
  await page.reload();
  await expect(page.getByRole("button", { name: "Mark as unread: Article 3" })).toBeVisible();
  await page.getByRole("button", { name: "Mark as unread: Article 3" }).click();
  await expect(page.getByRole("button", { name: "Mark as read: Article 3" })).toBeVisible();
  await page.reload();
  await expect(page.getByRole("button", { name: "Mark as read: Article 3" })).toBeVisible();
});

test("hide read removes read articles from the list and the count", async ({ page }) => {
  await page.getByRole("button", { name: "Mark as read: Article 2" }).click();
  await page.getByRole("button", { name: "Mark as read: Article 5" }).click();
  await page.getByLabel("Hide read").check();
  await expect(rows(page)).toHaveCount(8);
  await expect(page.getByRole("list", { name: "Articles" })).not.toContainText("Article 2");
  await expect(page.getByText("Showing 8 of 25")).toBeVisible();
  await page.getByLabel("Hide read").uncheck();
  await expect(rows(page)).toHaveCount(10);
  await expect(page.getByText("Showing 10 of 25")).toBeVisible();
});
