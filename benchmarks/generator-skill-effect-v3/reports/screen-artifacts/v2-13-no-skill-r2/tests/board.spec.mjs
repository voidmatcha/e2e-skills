import { expect, test } from "@playwright/test";

const card = (page, title) => page.locator("li.card", { hasText: title });
const column = (page, name) => page.getByRole("list", { name, exact: true });
const heading = (page, name) => page.locator(`section[data-column="${name}"] h2`);

test.beforeEach(async ({ page, request }) => {
  await request.post("/api/reset");
  await page.goto("/");
  await expect(heading(page, "Todo")).toBeVisible();
});

test("shows three columns with the seeded cards and counts", async ({ page }) => {
  await expect(page.locator("section.column")).toHaveCount(3);
  await expect(heading(page, "Todo")).toHaveText("Todo (4)");
  await expect(heading(page, "In progress")).toHaveText("In progress (2)");
  await expect(heading(page, "Done")).toHaveText("Done (1)");
  await expect(page.locator("li.card")).toHaveCount(7);
  await expect(column(page, "Todo").locator("li.card")).toHaveCount(4);
  await expect(column(page, "In progress").locator("li.card")).toHaveCount(2);
  await expect(column(page, "Done").locator("li.card")).toHaveCount(1);
});

test("moves a card with its Move menu", async ({ page }) => {
  await page.getByLabel("Move Write spec").selectOption("Done");
  await expect(column(page, "Done").getByText("Write spec")).toBeVisible();
  await expect(column(page, "Todo").getByText("Write spec")).toHaveCount(0);
  await expect(page.getByText("Write spec")).toHaveCount(1);
  await expect(heading(page, "Todo")).toHaveText("Todo (3)");
  await expect(heading(page, "Done")).toHaveText("Done (2)");
});

test("moves a card by dragging it onto a column", async ({ page }) => {
  await card(page, "Design logo").dragTo(page.locator('section[data-column="In progress"]'));
  await expect(column(page, "In progress").getByText("Design logo")).toBeVisible();
  await expect(column(page, "Todo").getByText("Design logo")).toHaveCount(0);
  await expect(heading(page, "Todo")).toHaveText("Todo (3)");
  await expect(heading(page, "In progress")).toHaveText("In progress (3)");
});

test("refuses a fourth card in In progress via the menu", async ({ page }) => {
  await page.getByLabel("Move Write spec").selectOption("In progress");
  await expect(heading(page, "In progress")).toHaveText("In progress (3)");
  await page.getByLabel("Move Design logo").selectOption("In progress");
  await expect(page.getByRole("alert")).toHaveText("In progress is full (limit 3)");
  await expect(column(page, "Todo").getByText("Design logo")).toBeVisible();
  await expect(column(page, "In progress").getByText("Design logo")).toHaveCount(0);
  await expect(heading(page, "In progress")).toHaveText("In progress (3)");
  await expect(heading(page, "Todo")).toHaveText("Todo (3)");
});

test("refuses a fourth card in In progress via drag and drop", async ({ page }) => {
  const target = page.locator('section[data-column="In progress"]');
  await card(page, "Write spec").dragTo(target);
  await expect(heading(page, "In progress")).toHaveText("In progress (3)");
  await card(page, "Set up CI").dragTo(target);
  await expect(page.getByRole("alert")).toHaveText("In progress is full (limit 3)");
  await expect(column(page, "Todo").getByText("Set up CI")).toBeVisible();
  await expect(heading(page, "In progress")).toHaveText("In progress (3)");
});

test("persists moves across a reload", async ({ page }) => {
  await page.getByLabel("Move Ship v1.0").selectOption("Todo");
  await expect(heading(page, "Todo")).toHaveText("Todo (5)");
  await page.reload();
  await expect(heading(page, "Todo")).toHaveText("Todo (5)");
  await expect(heading(page, "Done")).toHaveText("Done (0)");
  await expect(column(page, "Todo").getByText("Ship v1.0")).toBeVisible();
});

test("does not persist a refused move across a reload", async ({ page }) => {
  await page.getByLabel("Move Write spec").selectOption("In progress");
  await page.getByLabel("Move Design logo").selectOption("In progress");
  await expect(page.getByRole("alert")).toHaveText("In progress is full (limit 3)");
  await page.reload();
  await expect(heading(page, "In progress")).toHaveText("In progress (3)");
  await expect(column(page, "Todo").getByText("Design logo")).toBeVisible();
});
