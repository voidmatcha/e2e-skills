import { expect, test } from "@playwright/test";

const TITLES = ["Write report", "Book flights", "Call plumber"];

test.beforeEach(async ({ page, request }) => {
  // Disposable state: restore the three open tasks before every test.
  const reset = await request.post("/api/reset");
  expect(reset.ok()).toBe(true);
  await page.goto("/");
  await expect(page.getByRole("list", { name: "Open tasks" }).getByRole("listitem")).toHaveCount(3);
});

const openList = (page) => page.getByRole("list", { name: "Open tasks" });
const doneList = (page) => page.getByRole("list", { name: "Done tasks" });

async function markDone(page, title) {
  const write = page.waitForRequest(
    (r) => r.method() === "POST" && /\/api\/tasks\/\d+\/done$/.test(r.url()),
  );
  await page.getByRole("button", { name: `Mark ${title}` }).click();
  await write;
}

async function undo(page, title) {
  const write = page.waitForRequest(
    (r) => r.method() === "POST" && /\/api\/tasks\/\d+\/undo$/.test(r.url()),
  );
  await page.getByRole("button", { name: `Undo ${title}` }).click();
  await write;
}

test("starts with three open tasks and none done", async ({ page }) => {
  await expect(openList(page).getByRole("listitem")).toHaveText([
    /Write report/,
    /Book flights/,
    /Call plumber/,
  ]);
  await expect(doneList(page).getByRole("listitem")).toHaveCount(0);
});

test("mark done moves a task from Open to Done", async ({ page }) => {
  await markDone(page, "Book flights");

  await expect(doneList(page).getByRole("listitem")).toHaveText([/Book flights/]);
  await expect(openList(page).getByRole("listitem")).toHaveText([/Write report/, /Call plumber/]);
});

test("progress line counts completed tasks", async ({ page }) => {
  await expect(page.getByText("0 of 3 done")).toBeVisible();

  await markDone(page, "Write report");
  await expect(page.getByText("1 of 3 done")).toBeVisible();

  await markDone(page, "Call plumber");
  await expect(page.getByText("2 of 3 done")).toBeVisible();

  await undo(page, "Write report");
  await expect(page.getByText("1 of 3 done")).toBeVisible();
});

test("undo moves a done task back to Open", async ({ page }) => {
  await markDone(page, "Write report");
  await expect(doneList(page).getByRole("listitem")).toHaveText([/Write report/]);

  await undo(page, "Write report");

  await expect(doneList(page).getByRole("listitem")).toHaveCount(0);
  await expect(openList(page).getByRole("listitem")).toHaveText([
    /Write report/,
    /Book flights/,
    /Call plumber/,
  ]);
});

test("done state is stored on the server and survives a reload", async ({ page }) => {
  await markDone(page, "Call plumber");
  await expect(doneList(page).getByRole("listitem")).toHaveText([/Call plumber/]);

  await page.reload();

  await expect(doneList(page).getByRole("listitem")).toHaveText([/Call plumber/]);
  await expect(openList(page).getByRole("listitem")).toHaveText([/Write report/, /Book flights/]);
  await expect(page.getByText("1 of 3 done")).toBeVisible();
});

test("undone state is stored on the server and survives a reload", async ({ page }) => {
  await markDone(page, "Call plumber");
  await undo(page, "Call plumber");
  await expect(openList(page).getByRole("listitem")).toHaveCount(3);

  await page.reload();

  await expect(openList(page).getByRole("listitem")).toHaveText([
    /Write report/,
    /Book flights/,
    /Call plumber/,
  ]);
  await expect(doneList(page).getByRole("listitem")).toHaveCount(0);
  await expect(page.getByText("0 of 3 done")).toBeVisible();
});

test("a task is never in both lists, before or after a reload", async ({ page }) => {
  await markDone(page, "Book flights");
  await expect(doneList(page).getByRole("listitem")).toHaveCount(1);

  const inBoth = async () => {
    for (const title of TITLES) {
      const open = await openList(page).getByRole("listitem").filter({ hasText: title }).count();
      const done = await doneList(page).getByRole("listitem").filter({ hasText: title }).count();
      expect(open + done, title).toBe(1);
    }
  };
  await inBoth();

  await page.reload();
  await expect(openList(page).getByRole("listitem")).toHaveCount(2);
  await inBoth();

  await undo(page, "Book flights");
  await expect(openList(page).getByRole("listitem")).toHaveCount(3);
  await inBoth();
});
