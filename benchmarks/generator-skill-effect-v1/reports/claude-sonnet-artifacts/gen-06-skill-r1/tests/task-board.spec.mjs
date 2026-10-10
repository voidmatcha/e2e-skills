import { expect, test } from "@playwright/test";

const TASKS = ["Write report", "Book flights", "Call plumber"];

test.beforeEach(async ({ page, request }) => {
  const reset = await request.post("/api/reset");
  expect(reset.ok()).toBeTruthy();
  await page.goto("/");
  await expect(page.getByRole("list", { name: "Open tasks" }).getByRole("listitem")).toHaveCount(3);
});

const openList = (page) => page.getByRole("list", { name: "Open tasks" });
const doneList = (page) => page.getByRole("list", { name: "Done tasks" });

test("starts with three open tasks and none done", async ({ page }) => {
  await expect(openList(page).getByRole("listitem")).toHaveText(TASKS.map((t) => new RegExp(`^${t}`)));
  await expect(doneList(page).getByRole("listitem")).toHaveCount(0);
  await expect(page.getByText("0 of 3 done")).toBeVisible();
});

test("Mark done moves a task to the Done list and updates progress", async ({ page }) => {
  await page.getByRole("button", { name: "Mark Book flights" }).click();

  await expect(doneList(page).getByRole("listitem")).toHaveText([/^Book flights/]);
  await expect(openList(page).getByRole("listitem")).toHaveText([/^Write report/, /^Call plumber/]);
  await expect(page.getByText("1 of 3 done")).toBeVisible();

  await page.getByRole("button", { name: "Mark Write report" }).click();
  await expect(doneList(page).getByRole("listitem")).toHaveCount(2);
  await expect(page.getByText("2 of 3 done")).toBeVisible();
});

test("Undo moves a done task back to the Open list", async ({ page }) => {
  await page.getByRole("button", { name: "Mark Call plumber" }).click();
  await expect(page.getByText("1 of 3 done")).toBeVisible();

  await page.getByRole("button", { name: "Undo Call plumber" }).click();

  await expect(doneList(page).getByRole("listitem")).toHaveCount(0);
  await expect(openList(page).getByRole("listitem")).toHaveText(TASKS.map((t) => new RegExp(`^${t}`)));
  await expect(openList(page).getByText("Call plumber")).toBeVisible();
  await expect(page.getByText("0 of 3 done")).toBeVisible();
});

test("done state is stored on the server and survives a reload", async ({ page }) => {
  await page.getByRole("button", { name: "Mark Write report" }).click();
  await expect(page.getByText("1 of 3 done")).toBeVisible();

  await page.reload();

  await expect(doneList(page).getByRole("listitem")).toHaveText([/^Write report/]);
  await expect(openList(page).getByRole("listitem")).toHaveText([/^Book flights/, /^Call plumber/]);
  await expect(page.getByText("1 of 3 done")).toBeVisible();
});

test("undone state is stored on the server and survives a reload", async ({ page }) => {
  await page.getByRole("button", { name: "Mark Write report" }).click();
  await page.getByRole("button", { name: "Mark Book flights" }).click();
  await expect(page.getByText("2 of 3 done")).toBeVisible();
  await page.getByRole("button", { name: "Undo Write report" }).click();
  await expect(page.getByText("1 of 3 done")).toBeVisible();

  await page.reload();

  await expect(doneList(page).getByRole("listitem")).toHaveText([/^Book flights/]);
  await expect(openList(page).getByRole("listitem")).toHaveText([/^Write report/, /^Call plumber/]);
  await expect(page.getByText("1 of 3 done")).toBeVisible();
});

test("a task is never in both lists at once", async ({ page }) => {
  const everywhere = (title) => page.getByRole("listitem").filter({ hasText: title });

  await page.getByRole("button", { name: "Mark Book flights" }).click();
  await expect(doneList(page).getByText("Book flights")).toBeVisible();
  await expect(openList(page).getByText("Book flights")).toHaveCount(0);
  await expect(everywhere("Book flights")).toHaveCount(1);

  await page.getByRole("button", { name: "Undo Book flights" }).click();
  await expect(openList(page).getByText("Book flights")).toBeVisible();
  await expect(doneList(page).getByText("Book flights")).toHaveCount(0);
  await expect(everywhere("Book flights")).toHaveCount(1);
});
