import { expect, test } from "@playwright/test";

const column = (page, name) => page.getByRole("list", { name, exact: true });
const cards = (page, name) => column(page, name).getByRole("listitem");
const heading = (page, name) => page.getByRole("heading", { name: new RegExp(`^${name} \\(\\d+\\)$`) });

test.beforeEach(async ({ page }) => {
  await page.request.post("/api/reset");
  await page.goto("/");
  await expect(cards(page, "Todo")).toHaveCount(4);
});

test("the move menu moves a card and updates the counts", async ({ page }) => {
  await page.getByLabel("Move Write spec").selectOption("Done");
  await expect(cards(page, "Done")).toHaveText([/Write spec/, /Ship v1.0/]);
  await expect(cards(page, "Todo")).toHaveCount(3);
  await expect(column(page, "Todo")).not.toContainText("Write spec");
  await expect(heading(page, "Todo")).toHaveText("Todo (3)");
  await expect(heading(page, "Done")).toHaveText("Done (2)");
});

test("dragging a card onto a column moves it", async ({ page }) => {
  await cards(page, "Todo").filter({ hasText: "Design logo" }).dragTo(column(page, "Done"));
  await expect(cards(page, "Done")).toContainText([/Design logo/]);
  await expect(cards(page, "Todo")).toHaveCount(3);
  await expect(heading(page, "In progress")).toHaveText("In progress (2)");
});

test("in progress refuses a fourth card", async ({ page }) => {
  await page.getByLabel("Move Write spec").selectOption("In progress");
  await expect(cards(page, "In progress")).toHaveCount(3);
  await page.getByLabel("Move Design logo").selectOption("In progress");
  await expect(page.getByRole("alert")).toHaveText("In progress is full (limit 3)");
  await expect(cards(page, "In progress")).toHaveCount(3);
  await expect(cards(page, "Todo")).toContainText([/Design logo/]);
  await expect(heading(page, "In progress")).toHaveText("In progress (3)");
  await expect(heading(page, "Todo")).toHaveText("Todo (3)");
});

test("moves survive a reload", async ({ page }) => {
  await page.getByLabel("Move Set up CI").selectOption("Done");
  await expect(cards(page, "Done")).toContainText([/Set up CI/]);
  await page.reload();
  await expect(cards(page, "Done")).toContainText([/Set up CI/]);
  await expect(cards(page, "Todo")).toHaveCount(3);
  await expect(heading(page, "Done")).toHaveText("Done (2)");
});
