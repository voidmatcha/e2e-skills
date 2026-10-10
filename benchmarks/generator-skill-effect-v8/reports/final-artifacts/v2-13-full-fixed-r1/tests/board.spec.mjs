import { expect, test } from "@playwright/test";

const columns = {
  todo: "Todo",
  inProgress: "In progress",
  done: "Done",
};

function columnList(page, name) {
  return page.getByRole("list", { name, exact: true });
}

function columnHeading(page, name, count) {
  return page.getByRole("heading", { name: `${name} (${count})`, exact: true });
}

function cardInColumn(page, column, title) {
  return columnList(page, column).getByRole("listitem").filter({ hasText: title });
}

async function resetBoard(request) {
  const response = await request.post("/api/reset");
  expect(response.ok()).toBe(true);
}

async function openBoard(page) {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Sprint board", exact: true })).toBeVisible();
}

async function moveWithMenu(page, title, targetColumn) {
  const moveRequest = page.waitForRequest(
    (request) =>
      request.method() === "POST" &&
      request.url().includes("/api/cards/") &&
      request.url().endsWith("/move"),
  );
  const moveResponse = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      response.url().includes("/api/cards/") &&
      response.url().endsWith("/move"),
  );

  await page.getByLabel(`Move ${title}`).selectOption(targetColumn);

  return {
    request: await moveRequest,
    response: await moveResponse,
  };
}

test.beforeEach(async ({ request }) => {
  await resetBoard(request);
});

test("shows the seeded sprint board columns and cards", async ({ page }) => {
  await openBoard(page);

  await expect(columnHeading(page, columns.todo, 4)).toBeVisible();
  await expect(columnHeading(page, columns.inProgress, 2)).toBeVisible();
  await expect(columnHeading(page, columns.done, 1)).toBeVisible();
  await expect(columnList(page, columns.todo).getByRole("listitem")).toHaveCount(4);
  await expect(columnList(page, columns.inProgress).getByRole("listitem")).toHaveCount(2);
  await expect(columnList(page, columns.done).getByRole("listitem")).toHaveCount(1);
  await expect(cardInColumn(page, columns.todo, "Write spec")).toHaveCount(1);
  await expect(cardInColumn(page, columns.inProgress, "Fix login bug")).toHaveCount(1);
  await expect(cardInColumn(page, columns.done, "Ship v1.0")).toHaveCount(1);
});

test("moves a card with its Move menu and keeps it after reload", async ({ page }) => {
  await openBoard(page);

  const { request, response } = await moveWithMenu(page, "Write spec", columns.done);

  expect(request.postDataJSON()).toEqual({ column: columns.done });
  expect(response.status()).toBe(200);
  await expect(cardInColumn(page, columns.done, "Write spec")).toHaveCount(1);
  await expect(cardInColumn(page, columns.todo, "Write spec")).toHaveCount(0);
  await expect(columnHeading(page, columns.todo, 3)).toBeVisible();
  await expect(columnHeading(page, columns.done, 2)).toBeVisible();

  await page.reload();

  await expect(cardInColumn(page, columns.done, "Write spec")).toHaveCount(1);
  await expect(cardInColumn(page, columns.todo, "Write spec")).toHaveCount(0);
  await expect(columnHeading(page, columns.todo, 3)).toBeVisible();
  await expect(columnHeading(page, columns.done, 2)).toBeVisible();
});

test("moves a card by dragging it onto another column", async ({ page }) => {
  await openBoard(page);

  const card = cardInColumn(page, columns.todo, "Design logo");
  const moveResponse = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      response.url().includes("/api/cards/2/move"),
  );

  await card.dragTo(columnList(page, columns.done));

  const response = await moveResponse;
  expect(response.status()).toBe(200);
  await expect(cardInColumn(page, columns.done, "Design logo")).toHaveCount(1);
  await expect(cardInColumn(page, columns.todo, "Design logo")).toHaveCount(0);
  await expect(columnHeading(page, columns.todo, 3)).toBeVisible();
  await expect(columnHeading(page, columns.done, 2)).toBeVisible();
});

test("refuses moving a fourth card into In progress", async ({ page }) => {
  await openBoard(page);

  await moveWithMenu(page, "Write spec", columns.inProgress);
  await expect(columnHeading(page, columns.inProgress, 3)).toBeVisible();

  const { request, response } = await moveWithMenu(page, "Design logo", columns.inProgress);

  expect(request.postDataJSON()).toEqual({ column: columns.inProgress });
  expect(response.status()).toBe(409);
  await expect(page.getByRole("alert")).toHaveText("In progress is full (limit 3)");
  await expect(cardInColumn(page, columns.todo, "Design logo")).toHaveCount(1);
  await expect(cardInColumn(page, columns.inProgress, "Design logo")).toHaveCount(0);
  await expect(columnHeading(page, columns.todo, 3)).toBeVisible();
  await expect(columnHeading(page, columns.inProgress, 3)).toBeVisible();

  await page.reload();

  await expect(cardInColumn(page, columns.todo, "Design logo")).toHaveCount(1);
  await expect(cardInColumn(page, columns.inProgress, "Design logo")).toHaveCount(0);
  await expect(columnHeading(page, columns.todo, 3)).toBeVisible();
  await expect(columnHeading(page, columns.inProgress, 3)).toBeVisible();
});
