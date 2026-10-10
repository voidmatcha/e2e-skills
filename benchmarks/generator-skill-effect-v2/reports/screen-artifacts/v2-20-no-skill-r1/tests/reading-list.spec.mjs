import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page, request }) => {
  const res = await request.post("/api/reset");
  expect(res.ok()).toBeTruthy();
  await page.goto("/");
  await expect(page.getByText("Showing 10 of 25")).toBeVisible();
});

const items = (page) => page.getByRole("list", { name: "Articles" }).getByRole("listitem");
const titles = (page) => items(page).locator("span").allTextContents();
const loadMore = (page) => page.getByRole("button", { name: "Load more" });

test("loads ten articles initially", async ({ page }) => {
  await expect(items(page)).toHaveCount(10);
  await expect(items(page).first()).toContainText("Article 1");
  await expect(items(page).last()).toContainText("Article 10");
  await expect(loadMore(page)).toBeEnabled();
});

test("Load more pages through all 25 without repeats and then disables", async ({ page }) => {
  await loadMore(page).click();
  await expect(page.getByText("Showing 20 of 25")).toBeVisible();
  await expect(items(page)).toHaveCount(20);
  await expect(loadMore(page)).toBeEnabled();

  await loadMore(page).click();
  await expect(page.getByText("Showing 25 of 25")).toBeVisible();
  await expect(items(page)).toHaveCount(25);
  await expect(loadMore(page)).toBeDisabled();

  const all = await titles(page);
  expect(all).toEqual(Array.from({ length: 25 }, (_, i) => `Article ${i + 1}`));
  expect(new Set(all).size).toBe(25);
});

test("Mark as read toggles the button and back", async ({ page }) => {
  const row = items(page).filter({ has: page.getByText("Article 3", { exact: true }) });
  await row.getByRole("button", { name: "Mark as read" }).click();
  await expect(row.getByRole("button", { name: "Mark as unread" })).toBeVisible();
  await expect(row).toHaveClass(/read/);

  await row.getByRole("button", { name: "Mark as unread" }).click();
  await expect(row.getByRole("button", { name: "Mark as read" })).toBeVisible();
});

test("read state is stored on the server and survives reload", async ({ page }) => {
  const row = items(page).filter({ has: page.getByText("Article 2", { exact: true }) });
  await row.getByRole("button", { name: "Mark as read" }).click();
  await expect(row.getByRole("button", { name: "Mark as unread" })).toBeVisible();

  await page.reload();
  await expect(page.getByText("Showing 10 of 25")).toBeVisible();
  await expect(
    items(page).filter({ has: page.getByText("Article 2", { exact: true }) }).getByRole("button", { name: "Mark as unread" }),
  ).toBeVisible();
  await expect(
    items(page).filter({ has: page.getByText("Article 1", { exact: true }) }).getByRole("button", { name: "Mark as read" }),
  ).toBeVisible();
});

test("Hide read removes read articles from the list and the count", async ({ page }) => {
  for (const n of [1, 2]) {
    await page.getByRole("button", { name: `Mark as read: Article ${n}`, exact: true }).click();
    await expect(page.getByRole("button", { name: `Mark as unread: Article ${n}`, exact: true })).toBeVisible();
  }
  await expect(page.getByText("Showing 10 of 25")).toBeVisible();

  await page.getByLabel("Hide read").check();
  await expect(page.getByText("Showing 8 of 25")).toBeVisible();
  await expect(items(page)).toHaveCount(8);
  expect(await titles(page)).not.toContain("Article 1");
  expect(await titles(page)).not.toContain("Article 2");

  await page.getByLabel("Hide read").uncheck();
  await expect(page.getByText("Showing 10 of 25")).toBeVisible();
  await expect(items(page)).toHaveCount(10);
});

test("marking an article read while Hide read is on removes it immediately", async ({ page }) => {
  await page.getByLabel("Hide read").check();
  await page.getByRole("button", { name: "Mark as read: Article 5", exact: true }).click();
  await expect(page.getByText("Showing 9 of 25")).toBeVisible();
  await expect(items(page).filter({ has: page.getByText("Article 5", { exact: true }) })).toHaveCount(0);
});
