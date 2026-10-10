import { expect, test } from "@playwright/test";

const TITLES = ["Write report", "Book flights", "Call plumber"];

test.beforeEach(async ({ page, request }) => {
  const res = await request.post("/api/reset");
  expect(res.ok()).toBeTruthy();
  await page.goto("/");
  await expect(page.getByLabel("Open tasks").getByRole("listitem")).toHaveCount(3);
});

const open = (page) => page.getByLabel("Open tasks");
const done = (page) => page.getByLabel("Done tasks");
const progress = (page) => page.locator("#tb-progress");

test("starts with three open tasks and none done", async ({ page }) => {
  for (const title of TITLES) await expect(open(page).getByText(title)).toBeVisible();
  await expect(done(page).getByRole("listitem")).toHaveCount(0);
  await expect(progress(page)).toHaveText("0 of 3 done");
});

test("Mark done moves a task from Open to Done", async ({ page }) => {
  await page.getByRole("button", { name: "Mark Book flights" }).click();
  await expect(done(page).getByText("Book flights")).toBeVisible();
  await expect(open(page).getByText("Book flights")).toHaveCount(0);
  await expect(open(page).getByRole("listitem")).toHaveCount(2);
});

test("progress line counts done tasks", async ({ page }) => {
  await page.getByRole("button", { name: "Mark Write report" }).click();
  await expect(progress(page)).toHaveText("1 of 3 done");
  await page.getByRole("button", { name: "Mark Call plumber" }).click();
  await expect(progress(page)).toHaveText("2 of 3 done");
  await page.getByRole("button", { name: "Mark Book flights" }).click();
  await expect(progress(page)).toHaveText("3 of 3 done");
  await page.getByRole("button", { name: "Undo Call plumber" }).click();
  await expect(progress(page)).toHaveText("2 of 3 done");
});

test("Undo moves a done task back to Open", async ({ page }) => {
  await page.getByRole("button", { name: "Mark Call plumber" }).click();
  await expect(done(page).getByText("Call plumber")).toBeVisible();
  await page.getByRole("button", { name: "Undo Call plumber" }).click();
  await expect(open(page).getByText("Call plumber")).toBeVisible();
  await expect(done(page).getByText("Call plumber")).toHaveCount(0);
  await expect(progress(page)).toHaveText("0 of 3 done");
});

test("done state persists on the server across reload", async ({ page }) => {
  await page.getByRole("button", { name: "Mark Write report" }).click();
  await expect(done(page).getByText("Write report")).toBeVisible();
  await page.reload();
  await expect(done(page).getByText("Write report")).toBeVisible();
  await expect(open(page).getByText("Write report")).toHaveCount(0);
  await expect(open(page).getByRole("listitem")).toHaveCount(2);
  await expect(progress(page)).toHaveText("1 of 3 done");
});

test("undone state persists on the server across reload", async ({ page }) => {
  await page.getByRole("button", { name: "Mark Write report" }).click();
  await page.getByRole("button", { name: "Undo Write report" }).click();
  await expect(open(page).getByText("Write report")).toBeVisible();
  await page.reload();
  await expect(open(page).getByRole("listitem")).toHaveCount(3);
  await expect(done(page).getByRole("listitem")).toHaveCount(0);
  await expect(progress(page)).toHaveText("0 of 3 done");
});

test("a task is never in both lists", async ({ page }) => {
  const check = async () => {
    for (const title of TITLES) {
      const inOpen = await open(page).getByText(title).count();
      const inDone = await done(page).getByText(title).count();
      expect(inOpen + inDone).toBe(1);
    }
    await expect(open(page).getByRole("listitem")).toHaveCount(
      3 - (await done(page).getByRole("listitem").count()),
    );
  };
  await check();
  await page.getByRole("button", { name: "Mark Book flights" }).click();
  await expect(done(page).getByText("Book flights")).toBeVisible();
  await check();
  await page.reload();
  await expect(progress(page)).toHaveText("1 of 3 done");
  await check();
  await page.getByRole("button", { name: "Undo Book flights" }).click();
  await expect(open(page).getByText("Book flights")).toBeVisible();
  await check();
});
