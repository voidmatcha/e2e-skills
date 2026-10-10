import { expect, test } from "@playwright/test";

const cards = {
  todo: ["Write spec", "Design logo", "Set up CI", "Draft blog post"],
  inProgress: ["Fix login bug", "Review PR 42"],
  done: ["Ship v1.0"],
};

const column = (page, name) => page.getByRole("list", { name });
const card = (page, title) => page.locator(".card", { hasText: title });

async function expectColumn(page, name, titles) {
  await expect(page.getByRole("heading", { name: `${name} (${titles.length})` })).toBeVisible();
  const list = column(page, name);
  await expect(list.locator(".card")).toHaveCount(titles.length);
  for (const title of titles) {
    await expect(list.getByText(title, { exact: true })).toBeVisible();
  }
}

test.beforeEach(async ({ page, request }) => {
  await request.post("/api/reset");
  await page.goto("/");
});

test("shows the seeded sprint board", async ({ page }) => {
  await expect(page.getByRole("heading", { name: "Sprint board" })).toBeVisible();

  await expectColumn(page, "Todo", cards.todo);
  await expectColumn(page, "In progress", cards.inProgress);
  await expectColumn(page, "Done", cards.done);
});

test("moves a card by dragging it to another column", async ({ page }) => {
  await card(page, "Write spec").dragTo(page.locator('section[data-column="Done"]'));

  await expectColumn(page, "Todo", ["Design logo", "Set up CI", "Draft blog post"]);
  await expectColumn(page, "Done", ["Write spec", "Ship v1.0"]);
  await expect(column(page, "Todo").getByText("Write spec", { exact: true })).toHaveCount(0);
});

test("moves a card with its Move menu and keeps it after reload", async ({ page }) => {
  await page.getByLabel("Move Design logo").selectOption("Done");

  await expectColumn(page, "Todo", ["Write spec", "Set up CI", "Draft blog post"]);
  await expectColumn(page, "Done", ["Design logo", "Ship v1.0"]);
  await expect(column(page, "Todo").getByText("Design logo", { exact: true })).toHaveCount(0);

  await page.reload();

  await expectColumn(page, "Todo", ["Write spec", "Set up CI", "Draft blog post"]);
  await expectColumn(page, "Done", ["Design logo", "Ship v1.0"]);
  await expect(column(page, "Todo").getByText("Design logo", { exact: true })).toHaveCount(0);
});

test("refuses a fourth card in In progress", async ({ page }) => {
  await page.getByLabel("Move Write spec").selectOption("In progress");
  await expectColumn(page, "Todo", ["Design logo", "Set up CI", "Draft blog post"]);
  await expectColumn(page, "In progress", ["Write spec", "Fix login bug", "Review PR 42"]);

  await page.getByLabel("Move Design logo").selectOption("In progress");

  await expect(page.getByRole("alert")).toHaveText("In progress is full (limit 3)");
  await expectColumn(page, "Todo", ["Design logo", "Set up CI", "Draft blog post"]);
  await expectColumn(page, "In progress", ["Write spec", "Fix login bug", "Review PR 42"]);
  await expect(column(page, "In progress").getByText("Design logo", { exact: true })).toHaveCount(0);
});
