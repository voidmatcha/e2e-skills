import { expect, test } from "@playwright/test";

const TITLES = ["Write report", "Book flights", "Call plumber"];

test.beforeEach(async ({ page, request }) => {
  const res = await request.post("/api/reset");
  expect(res.ok()).toBe(true);
  await page.goto("/");
  await expect(page.getByLabel("Open tasks").getByRole("listitem")).toHaveCount(3);
});

const lists = (page) => ({
  open: page.getByLabel("Open tasks"),
  done: page.getByLabel("Done tasks"),
  progress: page.locator("#tb-progress"),
});

async function expectNeverInBoth(page) {
  const { open, done } = lists(page);
  for (const title of TITLES) {
    const inOpen = await open.getByText(title, { exact: true }).count();
    const inDone = await done.getByText(title, { exact: true }).count();
    expect(inOpen + inDone, `${title} appears exactly once`).toBe(1);
  }
}

test("starts with three open tasks and 0 of 3 done", async ({ page }) => {
  const { open, done, progress } = lists(page);
  await expect(open.getByRole("listitem")).toHaveText([/Write report/, /Book flights/, /Call plumber/]);
  await expect(done.getByRole("listitem")).toHaveCount(0);
  await expect(progress).toHaveText("0 of 3 done");
});

test("Mark done moves a task from Open to Done", async ({ page }) => {
  const { open, done, progress } = lists(page);
  await page.getByRole("button", { name: "Mark Book flights" }).click();
  await expect(done.getByRole("listitem")).toHaveText([/Book flights/]);
  await expect(open.getByRole("listitem")).toHaveText([/Write report/, /Call plumber/]);
  await expect(progress).toHaveText("1 of 3 done");
  await expectNeverInBoth(page);
});

test("progress line counts each completed task", async ({ page }) => {
  const { done, progress } = lists(page);
  await page.getByRole("button", { name: "Mark Write report" }).click();
  await expect(progress).toHaveText("1 of 3 done");
  await page.getByRole("button", { name: "Mark Call plumber" }).click();
  await expect(progress).toHaveText("2 of 3 done");
  await page.getByRole("button", { name: "Mark Book flights" }).click();
  await expect(progress).toHaveText("3 of 3 done");
  await expect(done.getByRole("listitem")).toHaveCount(3);
  await expect(lists(page).open.getByRole("listitem")).toHaveCount(0);
  await expectNeverInBoth(page);
});

test("Undo moves a done task back to Open", async ({ page }) => {
  const { open, done, progress } = lists(page);
  await page.getByRole("button", { name: "Mark Write report" }).click();
  await expect(done.getByRole("listitem")).toHaveCount(1);
  await page.getByRole("button", { name: "Undo Write report" }).click();
  await expect(done.getByRole("listitem")).toHaveCount(0);
  await expect(open.getByRole("listitem")).toHaveCount(3);
  await expect(open.getByText("Write report", { exact: true })).toBeVisible();
  await expect(progress).toHaveText("0 of 3 done");
  await expectNeverInBoth(page);
});

test("done state persists on the server across reload", async ({ page }) => {
  const { open, done, progress } = lists(page);
  await page.getByRole("button", { name: "Mark Book flights" }).click();
  await expect(progress).toHaveText("1 of 3 done");
  await page.reload();
  await expect(done.getByRole("listitem")).toHaveText([/Book flights/]);
  await expect(open.getByRole("listitem")).toHaveText([/Write report/, /Call plumber/]);
  await expect(progress).toHaveText("1 of 3 done");
  await expectNeverInBoth(page);
});

test("undone state persists on the server across reload", async ({ page }) => {
  const { open, done, progress } = lists(page);
  await page.getByRole("button", { name: "Mark Book flights" }).click();
  await page.getByRole("button", { name: "Mark Call plumber" }).click();
  await expect(progress).toHaveText("2 of 3 done");
  await page.getByRole("button", { name: "Undo Book flights" }).click();
  await expect(progress).toHaveText("1 of 3 done");
  await page.reload();
  await expect(done.getByRole("listitem")).toHaveText([/Call plumber/]);
  await expect(open.getByRole("listitem")).toHaveText([/Write report/, /Book flights/]);
  await expect(progress).toHaveText("1 of 3 done");
  await expectNeverInBoth(page);
});

test("state is shared with a fresh page, not kept only in the client", async ({ page, browser }) => {
  await page.getByRole("button", { name: "Mark Write report" }).click();
  await expect(lists(page).progress).toHaveText("1 of 3 done");
  const other = await browser.newContext({ baseURL: "http://127.0.0.1:5107" });
  const otherPage = await other.newPage();
  await otherPage.goto("/");
  await expect(lists(otherPage).done.getByRole("listitem")).toHaveText([/Write report/]);
  await other.close();
});
