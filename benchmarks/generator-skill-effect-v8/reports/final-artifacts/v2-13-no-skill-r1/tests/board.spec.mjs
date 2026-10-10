import { expect, test } from "@playwright/test";

const columns = {
  todo: "Todo",
  inProgress: "In progress",
  done: "Done",
};

const seededCards = {
  [columns.todo]: ["Write spec", "Design logo", "Set up CI", "Draft blog post"],
  [columns.inProgress]: ["Fix login bug", "Review PR 42"],
  [columns.done]: ["Ship v1.0"],
};

const column = (page, name) => page.locator("section", { has: page.getByRole("heading", { name: new RegExp(`^${name} \\(\\d+\\)$`) }) });
const list = (page, name) => page.getByRole("list", { name });
const card = (page, title) => page.locator(".card", { hasText: title });

async function expectColumn(page, name, cards) {
  await expect(page.getByRole("heading", { name: `${name} (${cards.length})` })).toBeVisible();
  await expect(list(page, name).locator(".card span")).toHaveText(cards);
}

async function expectBoard(page, expected) {
  for (const [name, cards] of Object.entries(expected)) {
    await expectColumn(page, name, cards);
  }
}

test.beforeEach(async ({ request }) => {
  await request.post("/api/reset");
});

test("shows the seeded sprint board", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByRole("heading", { name: "Sprint board" })).toBeVisible();
  await expectBoard(page, seededCards);
});

test("moves a card with its Move menu and persists after reload", async ({ page }) => {
  await page.goto("/");

  await page.getByLabel("Move Write spec").selectOption(columns.done);

  await expectBoard(page, {
    [columns.todo]: ["Design logo", "Set up CI", "Draft blog post"],
    [columns.inProgress]: seededCards[columns.inProgress],
    [columns.done]: ["Write spec", "Ship v1.0"],
  });

  await page.reload();

  await expectBoard(page, {
    [columns.todo]: ["Design logo", "Set up CI", "Draft blog post"],
    [columns.inProgress]: seededCards[columns.inProgress],
    [columns.done]: ["Write spec", "Ship v1.0"],
  });
});

test("moves a card by dragging it onto another column", async ({ page }) => {
  await page.goto("/");

  await card(page, "Ship v1.0").dragTo(column(page, columns.todo));

  await expectBoard(page, {
    [columns.todo]: ["Write spec", "Design logo", "Set up CI", "Draft blog post", "Ship v1.0"],
    [columns.inProgress]: seededCards[columns.inProgress],
    [columns.done]: [],
  });
});

test("refuses a fourth card in In progress", async ({ page }) => {
  await page.goto("/");

  await page.getByLabel("Move Write spec").selectOption(columns.inProgress);
  await page.getByLabel("Move Design logo").selectOption(columns.inProgress);

  await expect(page.getByRole("alert")).toHaveText("In progress is full (limit 3)");
  await expectBoard(page, {
    [columns.todo]: ["Design logo", "Set up CI", "Draft blog post"],
    [columns.inProgress]: ["Write spec", "Fix login bug", "Review PR 42"],
    [columns.done]: seededCards[columns.done],
  });
});
