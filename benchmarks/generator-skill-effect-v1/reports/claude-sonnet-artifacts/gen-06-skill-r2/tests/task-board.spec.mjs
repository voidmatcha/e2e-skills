import { expect, test } from "@playwright/test";

const TASKS = ["Write report", "Book flights", "Call plumber"];

test.beforeEach(async ({ page, request }) => {
  const reset = await request.post("/api/reset");
  expect(reset.ok()).toBe(true);
  await page.goto("/");
  await expect(page.getByText("0 of 3 done")).toBeVisible();
});

const openList = (page) => page.getByRole("list", { name: "Open tasks" });
const doneList = (page) => page.getByRole("list", { name: "Done tasks" });
const markDone = (page, title) => page.getByRole("button", { name: `Mark ${title}` }).click();
const undo = (page, title) => page.getByRole("button", { name: `Undo ${title}` }).click();

test("starts with three open tasks and none done", async ({ page }) => {
  await expect(openList(page).getByRole("listitem")).toHaveText(
    TASKS.map((title) => new RegExp(title)),
  );
  await expect(doneList(page).getByRole("listitem")).toHaveCount(0);
});

test("Mark done moves a task from Open tasks to Done tasks", async ({ page }) => {
  await markDone(page, "Book flights");

  await expect(doneList(page).getByRole("listitem")).toHaveText([/Book flights/]);
  await expect(openList(page).getByRole("listitem")).toHaveText([/Write report/, /Call plumber/]);
  await expect(page.getByText("1 of 3 done")).toBeVisible();
});

test("progress line counts each completed task", async ({ page }) => {
  await markDone(page, "Write report");
  await expect(page.getByText("1 of 3 done")).toBeVisible();

  await markDone(page, "Call plumber");
  await expect(page.getByText("2 of 3 done")).toBeVisible();

  await markDone(page, "Book flights");
  await expect(page.getByText("3 of 3 done")).toBeVisible();
  await expect(openList(page).getByRole("listitem")).toHaveCount(0);
  await expect(doneList(page).getByRole("listitem")).toHaveCount(3);
});

test("Undo moves a done task back to Open tasks", async ({ page }) => {
  await markDone(page, "Call plumber");
  await markDone(page, "Write report");
  await expect(page.getByText("2 of 3 done")).toBeVisible();

  await undo(page, "Call plumber");

  await expect(openList(page).getByRole("listitem")).toHaveText([/Book flights/, /Call plumber/]);
  await expect(doneList(page).getByRole("listitem")).toHaveText([/Write report/]);
  await expect(page.getByText("1 of 3 done")).toBeVisible();
});

test("done state is stored on the server and survives a reload", async ({ page }) => {
  await markDone(page, "Write report");
  await expect(page.getByText("1 of 3 done")).toBeVisible();

  await page.reload();

  await expect(page.getByText("1 of 3 done")).toBeVisible();
  await expect(doneList(page).getByRole("listitem")).toHaveText([/Write report/]);
  await expect(openList(page).getByRole("listitem")).toHaveText([/Book flights/, /Call plumber/]);
});

test("undone state is stored on the server and survives a reload", async ({ page }) => {
  await markDone(page, "Write report");
  await markDone(page, "Book flights");
  await undo(page, "Write report");
  await expect(page.getByText("1 of 3 done")).toBeVisible();

  await page.reload();

  await expect(page.getByText("1 of 3 done")).toBeVisible();
  await expect(doneList(page).getByRole("listitem")).toHaveText([/Book flights/]);
  await expect(openList(page).getByRole("listitem")).toHaveText([/Write report/, /Call plumber/]);
});

test("a task is never shown in both lists at once", async ({ page }) => {
  const occurrences = page.getByRole("listitem").filter({ hasText: "Book flights" });

  await expect(occurrences).toHaveCount(1);
  await expect(openList(page).getByRole("listitem").filter({ hasText: "Book flights" })).toHaveCount(1);

  await markDone(page, "Book flights");
  await expect(occurrences).toHaveCount(1);
  await expect(openList(page).getByRole("listitem").filter({ hasText: "Book flights" })).toHaveCount(0);
  await expect(doneList(page).getByRole("listitem").filter({ hasText: "Book flights" })).toHaveCount(1);

  await undo(page, "Book flights");
  await expect(occurrences).toHaveCount(1);
  await expect(openList(page).getByRole("listitem").filter({ hasText: "Book flights" })).toHaveCount(1);
  await expect(doneList(page).getByRole("listitem").filter({ hasText: "Book flights" })).toHaveCount(0);

  await page.reload();
  await expect(occurrences).toHaveCount(1);
});
