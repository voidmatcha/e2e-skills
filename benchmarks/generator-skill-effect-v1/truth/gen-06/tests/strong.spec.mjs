import { expect, test } from "@playwright/test";

const open = (page) => page.getByRole("list", { name: "Open tasks" }).getByRole("listitem");
const done = (page) => page.getByRole("list", { name: "Done tasks" }).getByRole("listitem");

test.beforeEach(async ({ page }) => {
  await page.request.post("/api/reset");
  await page.goto("/");
  await expect(open(page)).toHaveCount(3);
});

test("mark done moves the task to the done list", async ({ page }) => {
  await page.getByRole("button", { name: "Mark Book flights" }).click();
  await expect(done(page)).toHaveText([/Book flights/]);
  await expect(open(page)).toHaveCount(2);
  await expect(open(page).filter({ hasText: "Book flights" })).toHaveCount(0);
});

test("progress counts done tasks", async ({ page }) => {
  await expect(page.getByText("0 of 3 done")).toBeVisible();
  await page.getByRole("button", { name: "Mark Write report" }).click();
  await expect(page.getByText("1 of 3 done")).toBeVisible();
  await page.getByRole("button", { name: "Mark Call plumber" }).click();
  await expect(page.getByText("2 of 3 done")).toBeVisible();
});

test("undo moves the task back", async ({ page }) => {
  await page.getByRole("button", { name: "Mark Call plumber" }).click();
  await expect(done(page)).toHaveCount(1);
  await page.getByRole("button", { name: "Undo Call plumber" }).click();
  await expect(done(page)).toHaveCount(0);
  await expect(open(page)).toHaveCount(3);
  await expect(page.getByText("0 of 3 done")).toBeVisible();
});

test("done state survives a reload", async ({ page }) => {
  await page.getByRole("button", { name: "Mark Write report" }).click();
  await expect(done(page)).toHaveText([/Write report/]);
  await page.reload();
  await expect(done(page)).toHaveText([/Write report/]);
  await expect(open(page)).toHaveCount(2);
  await expect(page.getByText("1 of 3 done")).toBeVisible();
});
