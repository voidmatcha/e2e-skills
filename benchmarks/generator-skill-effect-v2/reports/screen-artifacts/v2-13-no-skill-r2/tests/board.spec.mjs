import { expect, test } from "@playwright/test";

const column = (page, name) => page.getByRole("list", { name, exact: true });
const heading = (page, name) => page.getByRole("heading", { name: new RegExp(`^${name} \\(\\d+\\)$`) });

test.beforeEach(async ({ page, request }) => {
  const res = await request.post("/api/reset");
  expect(res.ok()).toBeTruthy();
  await page.goto("/");
  await expect(heading(page, "Todo")).toBeVisible();
});

test("shows three columns with the seeded cards and counts", async ({ page }) => {
  await expect(page.getByRole("heading", { name: "Todo (4)" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "In progress (2)" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Done (1)" })).toBeVisible();
  await expect(column(page, "Todo").getByRole("listitem")).toHaveCount(4);
  await expect(column(page, "In progress").getByRole("listitem")).toHaveCount(2);
  await expect(column(page, "Done").getByRole("listitem")).toHaveCount(1);
  await expect(column(page, "Done")).toContainText("Ship v1.0");
});

test("moves a card with its Move menu", async ({ page }) => {
  await page.getByLabel("Move Write spec").selectOption("Done");
  await expect(column(page, "Done")).toContainText("Write spec");
  await expect(column(page, "Todo")).not.toContainText("Write spec");
  await expect(page.getByRole("heading", { name: "Todo (3)" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Done (2)" })).toBeVisible();
});

test("moves a card by dragging it onto a column", async ({ page }) => {
  await column(page, "Todo").getByText("Design logo").dragTo(page.locator('section[data-column="In progress"]'));
  await expect(column(page, "In progress")).toContainText("Design logo");
  await expect(column(page, "Todo")).not.toContainText("Design logo");
  await expect(page.getByRole("heading", { name: "Todo (3)" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "In progress (3)" })).toBeVisible();
});

test("refuses a fourth card in In progress (menu)", async ({ page }) => {
  await page.getByLabel("Move Write spec").selectOption("In progress");
  await expect(page.getByRole("heading", { name: "In progress (3)" })).toBeVisible();
  await page.getByLabel("Move Design logo").selectOption("In progress");
  await expect(page.getByRole("alert")).toHaveText("In progress is full (limit 3)");
  await expect(column(page, "Todo")).toContainText("Design logo");
  await expect(column(page, "In progress")).not.toContainText("Design logo");
  await expect(page.getByRole("heading", { name: "In progress (3)" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Todo (3)" })).toBeVisible();
});

test("refuses a fourth card in In progress (drag)", async ({ page }) => {
  const target = page.locator('section[data-column="In progress"]');
  await column(page, "Todo").getByText("Write spec").dragTo(target);
  await expect(page.getByRole("heading", { name: "In progress (3)" })).toBeVisible();
  await column(page, "Todo").getByText("Set up CI").dragTo(target);
  await expect(page.getByRole("alert")).toHaveText("In progress is full (limit 3)");
  await expect(column(page, "Todo")).toContainText("Set up CI");
  await expect(column(page, "In progress")).not.toContainText("Set up CI");
});

test("persists moves across a reload", async ({ page }) => {
  await page.getByLabel("Move Set up CI").selectOption("Done");
  await expect(page.getByRole("heading", { name: "Done (2)" })).toBeVisible();
  await page.reload();
  await expect(page.getByRole("heading", { name: "Done (2)" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Todo (3)" })).toBeVisible();
  await expect(column(page, "Done")).toContainText("Set up CI");
  await expect(column(page, "Todo")).not.toContainText("Set up CI");
});

test("a refused move is not persisted", async ({ page }) => {
  await page.getByLabel("Move Write spec").selectOption("In progress");
  await expect(page.getByRole("heading", { name: "In progress (3)" })).toBeVisible();
  await page.getByLabel("Move Design logo").selectOption("In progress");
  await expect(page.getByRole("alert")).toHaveText("In progress is full (limit 3)");
  await page.reload();
  await expect(column(page, "Todo")).toContainText("Design logo");
  await expect(page.getByRole("heading", { name: "In progress (3)" })).toBeVisible();
});
