import { expect, test } from "@playwright/test";

const columnList = (page, name) => page.getByRole("list", { name });
const cardInColumn = (page, column, title) =>
  columnList(page, column).getByRole("listitem").filter({ hasText: title });
const moveMenu = (page, title) => page.getByLabel(`Move ${title}`);
const columnHeading = (page, name, count) => {
  return page.getByRole("heading", { name: `${name} (${count})`, exact: true });
};

test.describe("Sprint board", () => {
  test.beforeEach(async ({ page }) => {
    await page.request.post("/api/reset");
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Sprint board", exact: true })).toBeVisible();
  });

  test("shows the seeded columns, counts, and cards", async ({ page }) => {
    await expect(columnHeading(page, "Todo", 4)).toBeVisible();
    await expect(columnHeading(page, "In progress", 2)).toBeVisible();
    await expect(columnHeading(page, "Done", 1)).toBeVisible();

    await expect(columnList(page, "Todo").getByRole("listitem")).toHaveText([
      /Write spec/,
      /Design logo/,
      /Set up CI/,
      /Draft blog post/,
    ]);
    await expect(columnList(page, "In progress").getByRole("listitem")).toHaveText([
      /Fix login bug/,
      /Review PR 42/,
    ]);
    await expect(columnList(page, "Done").getByRole("listitem")).toHaveText([/Ship v1\.0/]);
  });

  test("moves a card with the Move menu and keeps it after reload", async ({ page }) => {
    const moveResponse = page.waitForResponse(
      (response) =>
        response.url().endsWith("/api/cards/1/move") &&
        response.request().method() === "POST",
    );

    await moveMenu(page, "Write spec").selectOption("Done");

    const response = await moveResponse;
    expect(response.status()).toBe(200);
    expect(response.request().postDataJSON()).toEqual({ column: "Done" });
    await expect(cardInColumn(page, "Done", "Write spec")).toHaveCount(1);
    await expect(cardInColumn(page, "Todo", "Write spec")).toHaveCount(0);
    await expect(cardInColumn(page, "In progress", "Write spec")).toHaveCount(0);
    await expect(columnHeading(page, "Todo", 3)).toBeVisible();
    await expect(columnHeading(page, "Done", 2)).toBeVisible();

    await page.reload();

    await expect(cardInColumn(page, "Done", "Write spec")).toHaveCount(1);
    await expect(cardInColumn(page, "Todo", "Write spec")).toHaveCount(0);
    await expect(cardInColumn(page, "In progress", "Write spec")).toHaveCount(0);
    await expect(columnHeading(page, "Todo", 3)).toBeVisible();
    await expect(columnHeading(page, "Done", 2)).toBeVisible();
  });

  test("moves a card by dragging it onto another column", async ({ page }) => {
    const moveResponse = page.waitForResponse(
      (response) =>
        response.url().endsWith("/api/cards/3/move") &&
        response.request().method() === "POST",
    );

    await cardInColumn(page, "Todo", "Set up CI").dragTo(columnList(page, "Done"));

    const response = await moveResponse;
    expect(response.status()).toBe(200);
    expect(response.request().postDataJSON()).toEqual({ column: "Done" });
    await expect(cardInColumn(page, "Done", "Set up CI")).toHaveCount(1);
    await expect(cardInColumn(page, "Todo", "Set up CI")).toHaveCount(0);
    await expect(cardInColumn(page, "In progress", "Set up CI")).toHaveCount(0);
    await expect(columnHeading(page, "Todo", 3)).toBeVisible();
    await expect(columnHeading(page, "Done", 2)).toBeVisible();
  });

  test("refuses a fourth In progress card and leaves it in Todo", async ({ page }) => {
    const acceptedMove = page.waitForResponse(
      (response) =>
        response.url().endsWith("/api/cards/1/move") &&
        response.request().method() === "POST",
    );
    await moveMenu(page, "Write spec").selectOption("In progress");
    expect((await acceptedMove).status()).toBe(200);
    await expect(columnHeading(page, "In progress", 3)).toBeVisible();

    const rejectedMove = page.waitForResponse(
      (response) =>
        response.url().endsWith("/api/cards/2/move") &&
        response.request().method() === "POST",
    );
    await moveMenu(page, "Design logo").selectOption("In progress");

    const response = await rejectedMove;
    expect(response.status()).toBe(409);
    expect(response.request().postDataJSON()).toEqual({ column: "In progress" });
    await expect(page.getByRole("alert")).toHaveText("In progress is full (limit 3)");

    await page.reload();

    await expect(cardInColumn(page, "Todo", "Design logo")).toHaveCount(1);
    await expect(cardInColumn(page, "In progress", "Design logo")).toHaveCount(0);
    await expect(columnHeading(page, "Todo", 3)).toBeVisible();
    await expect(columnHeading(page, "In progress", 3)).toBeVisible();
  });
});
