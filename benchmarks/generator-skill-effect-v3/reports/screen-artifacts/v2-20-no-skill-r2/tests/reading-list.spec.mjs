import { expect, test } from "@playwright/test";

const titles = (page) => page.locator("#rl-list li span").allTextContents();
const count = (page) => page.locator("#rl-count");
const more = (page) => page.getByRole("button", { name: "Load more" });

test.beforeEach(async ({ page, request }) => {
  await request.post("/api/reset");
  await page.goto("/");
  await expect(count(page)).toHaveText("Showing 10 of 25");
});

test("loads ten articles at a time without repeats and disables Load more at the end", async ({ page }) => {
  expect(await titles(page)).toEqual(Array.from({ length: 10 }, (_, i) => `Article ${i + 1}`));
  await expect(more(page)).toBeEnabled();

  await more(page).click();
  await expect(count(page)).toHaveText("Showing 20 of 25");
  await expect(more(page)).toBeEnabled();

  await more(page).click();
  await expect(count(page)).toHaveText("Showing 25 of 25");
  await expect(more(page)).toBeDisabled();

  const all = await titles(page);
  expect(all).toEqual(Array.from({ length: 25 }, (_, i) => `Article ${i + 1}`));
  expect(new Set(all).size).toBe(25);
});

test("Mark as read toggles and persists across reload", async ({ page }) => {
  const item = page.locator("#rl-list li", { hasText: /^Article 3/ });
  await item.getByRole("button", { name: "Mark as read" }).click();
  await expect(item.getByRole("button", { name: "Mark as unread" })).toBeVisible();

  await page.reload();
  await expect(count(page)).toHaveText("Showing 10 of 25");
  const reloaded = page.locator("#rl-list li", { hasText: /^Article 3/ });
  await expect(reloaded.getByRole("button", { name: "Mark as unread" })).toBeVisible();

  await reloaded.getByRole("button", { name: "Mark as unread" }).click();
  await expect(reloaded.getByRole("button", { name: "Mark as read" })).toBeVisible();
  await page.reload();
  await expect(page.getByRole("button", { name: "Mark as read: Article 3", exact: true })).toBeVisible();
});

test("Hide read removes read articles from the list and the count", async ({ page }) => {
  await page.getByRole("button", { name: "Mark as read: Article 1", exact: true }).click();
  await page.getByRole("button", { name: "Mark as read: Article 2", exact: true }).click();
  await expect(count(page)).toHaveText("Showing 10 of 25");

  await page.getByLabel("Hide read").check();
  await expect(count(page)).toHaveText("Showing 8 of 25");
  const shown = await titles(page);
  expect(shown).not.toContain("Article 1");
  expect(shown).not.toContain("Article 2");
  expect(shown).toHaveLength(8);

  await page.getByLabel("Hide read").uncheck();
  await expect(count(page)).toHaveText("Showing 10 of 25");
});

test("Hide read applies to articles loaded afterwards", async ({ page }) => {
  await page.getByRole("button", { name: "Mark as read: Article 1", exact: true }).click();
  await page.getByLabel("Hide read").check();
  await more(page).click();
  await expect(count(page)).toHaveText("Showing 19 of 25");
  expect(await titles(page)).not.toContain("Article 1");
});
