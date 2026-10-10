import { expect, test } from "@playwright/test";

const cards = {
  todo: ["Write spec", "Design logo", "Set up CI", "Draft blog post"],
  inProgress: ["Fix login bug", "Review PR 42"],
  done: ["Ship v1.0"],
};

const columns = {
  todo: "Todo",
  inProgress: "In progress",
  done: "Done",
};

const exactName = (text) => new RegExp(`^${text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}$`);
const columnList = (page, column) => page.getByRole("list", { name: exactName(column) });
const cardInColumn = (page, column, title) => columnList(page, column).getByLabel(exactName(`Move ${title}`));
const cardNotInColumn = (page, column, title) => expect(cardInColumn(page, column, title)).toHaveCount(0);
const draggableCard = (page, column, title) => columnList(page, column).getByRole("listitem").filter({ hasText: title });
const heading = (page, text) => page.getByRole("heading", { name: exactName(text) });

test.beforeEach(async ({ page }) => {
  await page.request.post("/api/reset");
  await page.goto("/");
  await expect(heading(page, "Sprint board")).toBeVisible();
});

test("shows the seeded sprint board", async ({ page }) => {
  await expect(heading(page, "Todo (4)")).toBeVisible();
  await expect(heading(page, "In progress (2)")).toBeVisible();
  await expect(heading(page, "Done (1)")).toBeVisible();

  await expect(columnList(page, columns.todo).getByRole("listitem")).toContainText(cards.todo);
  await expect(columnList(page, columns.inProgress).getByRole("listitem")).toContainText(cards.inProgress);
  await expect(columnList(page, columns.done).getByRole("listitem")).toContainText(cards.done);
});

test("moves a card with its Move menu and persists after reload", async ({ page }) => {
  await expect(cardInColumn(page, columns.todo, "Write spec")).toBeVisible();

  const moveRequest = page.waitForRequest((request) => {
    if (request.method() !== "POST" || !request.url().endsWith("/api/cards/1/move")) return false;
    return request.postDataJSON().column === columns.done;
  });

  await page.getByLabel("Move Write spec").selectOption(columns.done);
  await moveRequest;

  await expect(heading(page, "Done (2)")).toBeVisible();
  await expect(cardInColumn(page, columns.done, "Write spec")).toBeVisible();
  await cardNotInColumn(page, columns.todo, "Write spec");
  await expect(columnList(page, columns.todo).getByRole("listitem")).toContainText(cards.todo.slice(1));

  await page.reload();
  await expect(heading(page, "Done (2)")).toBeVisible();
  await expect(cardInColumn(page, columns.done, "Write spec")).toBeVisible();
  await cardNotInColumn(page, columns.todo, "Write spec");
  await expect(columnList(page, columns.todo).getByRole("listitem")).toContainText(cards.todo.slice(1));
});

test("moves a card by dragging it to another column", async ({ page }) => {
  await expect(cardInColumn(page, columns.todo, "Design logo")).toBeVisible();

  const moveRequest = page.waitForRequest((request) => {
    if (request.method() !== "POST" || !request.url().endsWith("/api/cards/2/move")) return false;
    return request.postDataJSON().column === columns.done;
  });

  await draggableCard(page, columns.todo, "Design logo").dragTo(columnList(page, columns.done));
  await moveRequest;

  await expect(heading(page, "Done (2)")).toBeVisible();
  await expect(cardInColumn(page, columns.done, "Design logo")).toBeVisible();
  await cardNotInColumn(page, columns.todo, "Design logo");
  await expect(columnList(page, columns.todo).getByRole("listitem")).toContainText([
    "Write spec",
    "Set up CI",
    "Draft blog post",
  ]);
});

test("refuses a fourth card in In progress", async ({ page }) => {
  await page.getByLabel("Move Write spec").selectOption(columns.inProgress);
  await expect(heading(page, "In progress (3)")).toBeVisible();

  const rejectedMove = page.waitForResponse((response) => {
    return response.request().method() === "POST" && response.url().endsWith("/api/cards/2/move") && response.status() === 409;
  });

  await page.getByLabel("Move Design logo").selectOption(columns.inProgress);
  await rejectedMove;

  await expect(page.getByRole("alert")).toHaveText("In progress is full (limit 3)");
  await expect(cardInColumn(page, columns.todo, "Design logo")).toBeVisible();
  await expect(heading(page, "In progress (3)")).toBeVisible();

  await page.reload();
  await expect(cardInColumn(page, columns.todo, "Design logo")).toBeVisible();
  await expect(heading(page, "In progress (3)")).toBeVisible();
});
