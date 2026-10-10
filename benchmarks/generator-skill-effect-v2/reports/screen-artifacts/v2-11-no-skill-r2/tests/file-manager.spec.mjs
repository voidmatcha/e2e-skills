import { expect, test } from "@playwright/test";

const NAMES = ["budget.xlsx", "contract.pdf", "draft.docx", "logo.svg", "minutes.txt", "photo.jpg", "roadmap.md"];

test.beforeEach(async ({ page, request }) => {
  await request.post("/api/reset");
  await page.goto("/");
  await expect(page.getByRole("checkbox", { name: /^Select (?!all)/ })).toHaveCount(7);
});

const row = (page, name) => page.getByRole("checkbox", { name: `Select ${name}` });
const header = (page) => page.getByRole("checkbox", { name: "Select all files" });
const isIndeterminate = (page) => header(page).evaluate((el) => el.indeterminate);

test("lists the seven seeded files with nothing selected", async ({ page }) => {
  for (const name of NAMES) await expect(page.getByRole("cell", { name, exact: true })).toBeVisible();
  await expect(page.getByText("0 selected")).toBeVisible();
  await expect(page.getByRole("button", { name: "Delete selected" })).toBeDisabled();
});

test("row checkboxes update the selected count", async ({ page }) => {
  await row(page, "budget.xlsx").check();
  await expect(page.getByText("1 selected")).toBeVisible();
  await row(page, "logo.svg").check();
  await expect(page.getByText("2 selected")).toBeVisible();
  await row(page, "budget.xlsx").uncheck();
  await expect(page.getByText("1 selected")).toBeVisible();
});

test("header checkbox selects all rows and clears them", async ({ page }) => {
  await header(page).check();
  await expect(page.getByText("7 selected")).toBeVisible();
  for (const name of NAMES) await expect(row(page, name)).toBeChecked();
  await header(page).uncheck();
  await expect(page.getByText("0 selected")).toBeVisible();
  for (const name of NAMES) await expect(row(page, name)).not.toBeChecked();
});

test("header checkbox is indeterminate only while some rows are selected", async ({ page }) => {
  expect(await isIndeterminate(page)).toBe(false);
  await row(page, "draft.docx").check();
  await expect(page.getByText("1 selected")).toBeVisible();
  expect(await isIndeterminate(page)).toBe(true);
  await expect(header(page)).not.toBeChecked();
  await header(page).check();
  await expect(page.getByText("7 selected")).toBeVisible();
  expect(await isIndeterminate(page)).toBe(false);
  await row(page, "draft.docx").uncheck();
  expect(await isIndeterminate(page)).toBe(true);
  await header(page).check();
  await header(page).uncheck();
  expect(await isIndeterminate(page)).toBe(false);
});

test("dismissing the confirm dialog deletes nothing", async ({ page }) => {
  await row(page, "budget.xlsx").check();
  await row(page, "contract.pdf").check();
  let message;
  page.once("dialog", (dialog) => {
    message = dialog.message();
    return dialog.dismiss();
  });
  await page.getByRole("button", { name: "Delete selected" }).click();
  await expect.poll(() => message).toBe("Delete 2 files?");
  await expect(page.getByRole("checkbox", { name: /^Select (?!all)/ })).toHaveCount(7);
  await expect(page.getByText("2 selected")).toBeVisible();
  await expect(page.getByText("files deleted")).toBeHidden();
  await page.reload();
  await expect(page.getByRole("checkbox", { name: /^Select (?!all)/ })).toHaveCount(7);
});

test("confirming deletes the selected rows and shows the toast", async ({ page }) => {
  await row(page, "budget.xlsx").check();
  await row(page, "photo.jpg").check();
  await row(page, "roadmap.md").check();
  let message;
  page.once("dialog", (dialog) => {
    message = dialog.message();
    return dialog.accept();
  });
  await page.getByRole("button", { name: "Delete selected" }).click();
  await expect(page.getByText("3 files deleted")).toBeVisible();
  expect(message).toBe("Delete 3 files?");
  await expect(page.getByRole("button", { name: "Undo" })).toBeVisible();
  for (const name of ["budget.xlsx", "photo.jpg", "roadmap.md"]) await expect(row(page, name)).toHaveCount(0);
  for (const name of ["contract.pdf", "draft.docx", "logo.svg", "minutes.txt"]) await expect(row(page, name)).toBeVisible();
  await expect(page.getByText("0 selected")).toBeVisible();
  await page.reload();
  await expect(page.getByRole("checkbox", { name: /^Select (?!all)/ })).toHaveCount(4);
});

test("undo restores deleted files, including after a reload", async ({ page }) => {
  await header(page).check();
  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "Delete selected" }).click();
  await expect(page.getByText("7 files deleted")).toBeVisible();
  await expect(page.getByRole("checkbox", { name: /^Select (?!all)/ })).toHaveCount(0);
  await page.getByRole("button", { name: "Undo" }).click();
  await expect(page.getByText("7 files deleted")).toBeHidden();
  for (const name of NAMES) await expect(row(page, name)).toBeVisible();
  await page.reload();
  await expect(page.getByRole("checkbox", { name: /^Select (?!all)/ })).toHaveCount(7);
  for (const name of NAMES) await expect(row(page, name)).toBeVisible();
});
