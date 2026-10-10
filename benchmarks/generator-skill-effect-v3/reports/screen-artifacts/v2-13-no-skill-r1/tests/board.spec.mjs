import { expect, test } from "@playwright/test";

const column = (page, name) => page.getByRole("list", { name, exact: true });
const heading = (page, name) => page.getByRole("heading", { name: new RegExp(`^${name} \\(`) });

test.beforeEach(async ({ page, request }) => {
  const res = await request.post("/api/reset");
  expect(res.ok()).toBeTruthy();
  await page.goto("/");
  await expect(column(page, "Todo").getByRole("listitem")).toHaveCount(4);
});

test("shows three columns with the seeded cards and counts", async ({ page }) => {
  await expect(heading(page, "Todo")).toHaveText("Todo (4)");
  await expect(heading(page, "In progress")).toHaveText("In progress (2)");
  await expect(heading(page, "Done")).toHaveText("Done (1)");
  await expect(column(page, "Todo").getByRole("listitem")).toHaveCount(4);
  await expect(column(page, "In progress").getByRole("listitem")).toHaveCount(2);
  await expect(column(page, "Done").getByRole("listitem")).toHaveCount(1);
  await expect(column(page, "Done")).toContainText("Ship v1.0");
});

test("moves a card with its Move menu", async ({ page }) => {
  await page.getByLabel("Move Write spec").selectOption("Done");
  await expect(column(page, "Done")).toContainText("Write spec");
  await expect(column(page, "Todo")).not.toContainText("Write spec");
  await expect(heading(page, "Todo")).toHaveText("Todo (3)");
  await expect(heading(page, "Done")).toHaveText("Done (2)");
});

test("moves a card by dragging it onto a column", async ({ page }) => {
  await page.getByText("Design logo").dragTo(page.locator('section[data-column="Done"]'));
  await expect(column(page, "Done")).toContainText("Design logo");
  await expect(column(page, "Todo")).not.toContainText("Design logo");
  await expect(heading(page, "Todo")).toHaveText("Todo (3)");
  await expect(heading(page, "Done")).toHaveText("Done (2)");
});

test("refuses a fourth card in In progress", async ({ page }) => {
  await page.getByLabel("Move Write spec").selectOption("In progress");
  await expect(heading(page, "In progress")).toHaveText("In progress (3)");
  await page.getByLabel("Move Set up CI").selectOption("In progress");
  await expect(page.getByRole("alert")).toHaveText("In progress is full (limit 3)");
  await expect(column(page, "Todo")).toContainText("Set up CI");
  await expect(column(page, "In progress")).not.toContainText("Set up CI");
  await expect(heading(page, "In progress")).toHaveText("In progress (3)");
  await expect(heading(page, "Todo")).toHaveText("Todo (3)");
});

test("refuses a fourth card dropped onto In progress", async ({ page }) => {
  await page.getByLabel("Move Write spec").selectOption("In progress");
  await expect(heading(page, "In progress")).toHaveText("In progress (3)");
  await page.getByText("Set up CI").dragTo(page.locator('section[data-column="In progress"]'));
  await expect(page.getByRole("alert")).toHaveText("In progress is full (limit 3)");
  await expect(column(page, "Todo")).toContainText("Set up CI");
  await expect(heading(page, "In progress")).toHaveText("In progress (3)");
});

test("persists moves across a reload", async ({ page }) => {
  await page.getByLabel("Move Draft blog post").selectOption("Done");
  await expect(column(page, "Done")).toContainText("Draft blog post");
  await page.reload();
  await expect(column(page, "Done")).toContainText("Draft blog post");
  await expect(column(page, "Todo")).not.toContainText("Draft blog post");
  await expect(heading(page, "Todo")).toHaveText("Todo (3)");
  await expect(heading(page, "Done")).toHaveText("Done (2)");
});
