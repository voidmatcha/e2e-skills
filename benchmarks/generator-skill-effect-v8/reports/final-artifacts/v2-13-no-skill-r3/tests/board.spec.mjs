import { expect, test } from "@playwright/test";

const columns = {
  todo: "Todo",
  inProgress: "In progress",
  done: "Done",
};

const seededCards = {
  todo: ["Write spec", "Design logo", "Set up CI", "Draft blog post"],
  inProgress: ["Fix login bug", "Review PR 42"],
  done: ["Ship v1.0"],
};

test.beforeEach(async ({ page, request }) => {
  await request.post("/api/reset");
  await page.goto("/");
});

const columnList = (page, name) => page.getByRole("list", { name });
const columnDropTarget = (page, name) => page.locator(`section[data-column="${name}"]`);
const card = (page, title) => page.locator("li.card").filter({ hasText: title });

async function expectColumn(page, name, titles) {
  await expect(page.getByRole("heading", { name: `${name} (${titles.length})` })).toBeVisible();

  const list = columnList(page, name);
  await expect(list.getByRole("listitem")).toHaveCount(titles.length);
  for (const title of titles) {
    await expect(list.getByText(title, { exact: true })).toBeVisible();
  }
}

async function expectCardOnlyIn(page, title, targetColumn) {
  for (const column of Object.values(columns)) {
    const expectation = expect(columnList(page, column).getByText(title, { exact: true }));
    if (column === targetColumn) await expectation.toHaveCount(1);
    else await expectation.toHaveCount(0);
  }
}

test("shows the seeded columns and cards", async ({ page }) => {
  await expect(page.getByRole("heading", { name: "Sprint board" })).toBeVisible();
  await expectColumn(page, columns.todo, seededCards.todo);
  await expectColumn(page, columns.inProgress, seededCards.inProgress);
  await expectColumn(page, columns.done, seededCards.done);
});

test("moves a card with the Move menu and persists after reload", async ({ page }) => {
  await page.getByLabel("Move Write spec").selectOption(columns.done);

  await expectCardOnlyIn(page, "Write spec", columns.done);
  await expectColumn(page, columns.todo, ["Design logo", "Set up CI", "Draft blog post"]);
  await expectColumn(page, columns.done, ["Write spec", "Ship v1.0"]);

  await page.reload();

  await expectCardOnlyIn(page, "Write spec", columns.done);
  await expectColumn(page, columns.todo, ["Design logo", "Set up CI", "Draft blog post"]);
  await expectColumn(page, columns.done, ["Write spec", "Ship v1.0"]);
});

test("moves a card by dragging it onto another column", async ({ page }) => {
  await card(page, "Ship v1.0").dragTo(columnDropTarget(page, columns.todo));

  await expectCardOnlyIn(page, "Ship v1.0", columns.todo);
  await expectColumn(page, columns.todo, [...seededCards.todo, "Ship v1.0"]);
  await expectColumn(page, columns.done, []);
});

test("refuses to move a fourth card into In progress", async ({ page }) => {
  await page.getByLabel("Move Write spec").selectOption(columns.inProgress);
  await expectCardOnlyIn(page, "Write spec", columns.inProgress);
  await expectColumn(page, columns.inProgress, ["Write spec", ...seededCards.inProgress]);

  await page.getByLabel("Move Design logo").selectOption(columns.inProgress);

  await expect(page.getByRole("alert")).toHaveText("In progress is full (limit 3)");
  await expectCardOnlyIn(page, "Design logo", columns.todo);
  await expectColumn(page, columns.todo, ["Design logo", "Set up CI", "Draft blog post"]);
  await expectColumn(page, columns.inProgress, ["Write spec", ...seededCards.inProgress]);
});
