import { expect, test } from "@playwright/test";

const TITLES = ["Write report", "Book flights", "Call plumber"];

test.beforeEach(async ({ page, request }) => {
  const res = await request.post("/api/reset");
  expect(res.ok()).toBeTruthy();
  await page.goto("/");
  await expect(page.getByRole("list", { name: "Open tasks" }).getByRole("listitem")).toHaveCount(3);
});

const openList = (page) => page.getByRole("list", { name: "Open tasks" });
const doneList = (page) => page.getByRole("list", { name: "Done tasks" });
const progress = (page) => page.locator("#tb-progress");

async function expectLists(page, open, done) {
  await expect(openList(page).locator("li span")).toHaveText(open);
  await expect(doneList(page).locator("li span")).toHaveText(done);
  await expect(progress(page)).toHaveText(`${done.length} of 3 done`);
  // a task is never in both lists
  for (const title of TITLES) {
    await expect(page.locator("li.task", { hasText: title })).toHaveCount(1);
  }
}

test("starts with three open tasks and 0 of 3 done", async ({ page }) => {
  await expectLists(page, TITLES, []);
});

test("Mark done moves a task to the Done list", async ({ page }) => {
  await page.getByRole("button", { name: "Mark Book flights" }).click();
  await expectLists(page, ["Write report", "Call plumber"], ["Book flights"]);
});

test("progress line counts done tasks", async ({ page }) => {
  await page.getByRole("button", { name: "Mark Write report" }).click();
  await expect(progress(page)).toHaveText("1 of 3 done");
  await page.getByRole("button", { name: "Mark Call plumber" }).click();
  await expect(progress(page)).toHaveText("2 of 3 done");
  await page.getByRole("button", { name: "Mark Book flights" }).click();
  await expect(progress(page)).toHaveText("3 of 3 done");
  await expectLists(page, [], TITLES);
});

test("Undo moves a done task back to the Open list", async ({ page }) => {
  await page.getByRole("button", { name: "Mark Book flights" }).click();
  await expectLists(page, ["Write report", "Call plumber"], ["Book flights"]);
  await page.getByRole("button", { name: "Undo Book flights" }).click();
  await expect(doneList(page).getByRole("listitem")).toHaveCount(0);
  await expect(openList(page).getByRole("listitem")).toHaveCount(3);
  await expect(progress(page)).toHaveText("0 of 3 done");
  await expect(page.locator("li.task", { hasText: "Book flights" })).toHaveCount(1);
});

test("done state persists across reload", async ({ page }) => {
  await page.getByRole("button", { name: "Mark Write report" }).click();
  await expectLists(page, ["Book flights", "Call plumber"], ["Write report"]);
  await page.reload();
  await expectLists(page, ["Book flights", "Call plumber"], ["Write report"]);
});

test("undone state persists across reload", async ({ page }) => {
  await page.getByRole("button", { name: "Mark Write report" }).click();
  await page.getByRole("button", { name: "Mark Call plumber" }).click();
  await expectLists(page, ["Book flights"], ["Write report", "Call plumber"]);
  await page.getByRole("button", { name: "Undo Write report" }).click();
  await expectLists(page, ["Write report", "Book flights"], ["Call plumber"]);
  await page.reload();
  await expectLists(page, ["Write report", "Book flights"], ["Call plumber"]);
});

test("reset restores all tasks as open", async ({ page, request }) => {
  await page.getByRole("button", { name: "Mark Write report" }).click();
  await expect(progress(page)).toHaveText("1 of 3 done");
  await request.post("/api/reset");
  await page.reload();
  await expectLists(page, TITLES, []);
});
