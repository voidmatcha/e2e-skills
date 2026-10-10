import { expect, test } from "@playwright/test";

const rows = (page) => page.locator("tbody tr");
const all = (page) => page.getByLabel("Select all files");

test.beforeEach(async ({ page }) => {
  await page.request.post("/api/reset");
  await page.goto("/");
  await expect(rows(page)).toHaveCount(7);
});

test("select all selects every row and clears them", async ({ page }) => {
  await all(page).check();
  await expect(page.getByText("7 selected")).toBeVisible();
  for (const name of ["budget.xlsx", "roadmap.md"]) await expect(page.getByLabel(`Select ${name}`)).toBeChecked();
  await all(page).uncheck();
  await expect(page.getByText("0 selected")).toBeVisible();
  await expect(page.getByLabel("Select roadmap.md")).not.toBeChecked();
});

test("a partial selection makes the header indeterminate", async ({ page }) => {
  await page.getByLabel("Select draft.docx").check();
  await expect(page.getByText("1 selected")).toBeVisible();
  await expect(all(page)).toHaveJSProperty("indeterminate", true);
  await all(page).check();
  await expect(all(page)).toHaveJSProperty("indeterminate", false);
  await expect(all(page)).toBeChecked();
});

test("delete asks with the right count, dismiss keeps the files", async ({ page }) => {
  await page.getByLabel("Select draft.docx").check();
  await page.getByLabel("Select logo.svg").check();
  const messages = [];
  page.once("dialog", (dialog) => { messages.push(dialog.message()); dialog.dismiss(); });
  await page.getByRole("button", { name: "Delete selected" }).click();
  await expect.poll(() => messages).toEqual(["Delete 2 files?"]);
  await expect(rows(page)).toHaveCount(7);
});

test("confirming deletes, undo restores on the server", async ({ page }) => {
  await page.getByLabel("Select draft.docx").check();
  await page.getByLabel("Select logo.svg").check();
  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "Delete selected" }).click();
  await expect(rows(page)).toHaveCount(5);
  await expect(page.getByRole("status")).toContainText("2 files deleted");
  await page.reload();
  await expect(rows(page)).toHaveCount(5);
  await page.getByLabel("Select minutes.txt").check();
  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "Delete selected" }).click();
  await expect(rows(page)).toHaveCount(4);
  await page.getByRole("button", { name: "Undo" }).click();
  await expect(rows(page)).toHaveCount(5);
  await expect(page.getByText("minutes.txt")).toBeVisible();
  await page.reload();
  await expect(rows(page)).toHaveCount(5);
  await expect(page.getByText("minutes.txt")).toBeVisible();
});
