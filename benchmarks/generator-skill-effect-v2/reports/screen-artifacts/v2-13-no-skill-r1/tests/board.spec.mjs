import { expect, test } from "@playwright/test";

const column = (page, name) => page.locator(`section[data-column="${name}"]`);
const cardIn = (page, name, title) => column(page, name).getByRole("listitem").filter({ hasText: title });

test.beforeEach(async ({ page, request }) => {
  await request.post("/api/reset");
  await page.goto("/");
  await expect(column(page, "Todo").getByRole("heading")).toBeVisible();
});

test("shows three columns with the seeded cards and counts", async ({ page }) => {
  await expect(column(page, "Todo").getByRole("heading")).toHaveText("Todo (4)");
  await expect(column(page, "In progress").getByRole("heading")).toHaveText("In progress (2)");
  await expect(column(page, "Done").getByRole("heading")).toHaveText("Done (1)");
  await expect(page.getByRole("listitem")).toHaveCount(7);
  await expect(column(page, "Todo").getByRole("listitem")).toHaveCount(4);
  await expect(column(page, "In progress").getByRole("listitem")).toHaveCount(2);
  await expect(column(page, "Done").getByRole("listitem")).toHaveCount(1);
});

test("moves a card with its Move menu", async ({ page }) => {
  await page.getByLabel("Move Write spec").selectOption("Done");
  await expect(cardIn(page, "Done", "Write spec")).toHaveCount(1);
  await expect(page.getByRole("listitem").filter({ hasText: "Write spec" })).toHaveCount(1);
  await expect(column(page, "Todo").getByRole("heading")).toHaveText("Todo (3)");
  await expect(column(page, "Done").getByRole("heading")).toHaveText("Done (2)");
});

test("moves a card by dragging it onto a column", async ({ page }) => {
  await cardIn(page, "Todo", "Design logo").dragTo(column(page, "Done"));
  await expect(cardIn(page, "Done", "Design logo")).toHaveCount(1);
  await expect(page.getByRole("listitem").filter({ hasText: "Design logo" })).toHaveCount(1);
  await expect(column(page, "Todo").getByRole("heading")).toHaveText("Todo (3)");
  await expect(column(page, "Done").getByRole("heading")).toHaveText("Done (2)");
});

test("moves persist across a reload", async ({ page }) => {
  await page.getByLabel("Move Set up CI").selectOption("In progress");
  await expect(cardIn(page, "In progress", "Set up CI")).toHaveCount(1);
  await page.reload();
  await expect(cardIn(page, "In progress", "Set up CI")).toHaveCount(1);
  await expect(column(page, "In progress").getByRole("heading")).toHaveText("In progress (3)");
  await expect(column(page, "Todo").getByRole("heading")).toHaveText("Todo (3)");
});

test("refuses a fourth card in In progress via the Move menu", async ({ page }) => {
  await page.getByLabel("Move Set up CI").selectOption("In progress");
  await expect(column(page, "In progress").getByRole("heading")).toHaveText("In progress (3)");

  await page.getByLabel("Move Write spec").selectOption("In progress");
  await expect(page.getByRole("alert")).toHaveText("In progress is full (limit 3)");
  await expect(cardIn(page, "Todo", "Write spec")).toHaveCount(1);
  await expect(column(page, "In progress").getByRole("listitem")).toHaveCount(3);
  await expect(column(page, "In progress").getByRole("heading")).toHaveText("In progress (3)");
  await expect(column(page, "Todo").getByRole("heading")).toHaveText("Todo (3)");

  await page.reload();
  await expect(cardIn(page, "Todo", "Write spec")).toHaveCount(1);
  await expect(column(page, "In progress").getByRole("heading")).toHaveText("In progress (3)");
});

test("refuses a fourth card in In progress via drag and drop", async ({ page }) => {
  await cardIn(page, "Todo", "Set up CI").dragTo(column(page, "In progress"));
  await expect(column(page, "In progress").getByRole("heading")).toHaveText("In progress (3)");

  await cardIn(page, "Todo", "Draft blog post").dragTo(column(page, "In progress"));
  await expect(page.getByRole("alert")).toHaveText("In progress is full (limit 3)");
  await expect(cardIn(page, "Todo", "Draft blog post")).toHaveCount(1);
  await expect(column(page, "In progress").getByRole("listitem")).toHaveCount(3);
});
