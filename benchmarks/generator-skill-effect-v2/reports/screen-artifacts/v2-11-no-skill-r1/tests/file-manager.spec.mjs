import { expect, test } from "@playwright/test";

const NAMES = ["budget.xlsx", "contract.pdf", "draft.docx", "logo.svg", "minutes.txt", "photo.jpg", "roadmap.md"];

test.beforeEach(async ({ page, request }) => {
  await request.post("/api/reset");
  await page.goto("/");
  await expect(page.getByRole("checkbox", { name: "Select budget.xlsx" })).toBeVisible();
});

const rowBox = (page, name) => page.getByRole("checkbox", { name: `Select ${name}` });
const selectedText = (page) => page.locator("#fm-selected");
const headerBox = (page) => page.getByRole("checkbox", { name: "Select all files" });
const isIndeterminate = (page) => headerBox(page).evaluate((el) => el.indeterminate);

test("lists the seven seeded files with nothing selected", async ({ page }) => {
  await expect(page.locator("#fm-rows tr")).toHaveCount(7);
  for (const name of NAMES) await expect(page.getByRole("cell", { name, exact: true })).toBeVisible();
  await expect(selectedText(page)).toHaveText("0 selected");
  await expect(page.getByRole("button", { name: "Delete selected" })).toBeDisabled();
});

test("row checkboxes update the selected count", async ({ page }) => {
  await rowBox(page, "budget.xlsx").check();
  await expect(selectedText(page)).toHaveText("1 selected");
  await rowBox(page, "logo.svg").check();
  await expect(selectedText(page)).toHaveText("2 selected");
  await rowBox(page, "budget.xlsx").uncheck();
  await expect(selectedText(page)).toHaveText("1 selected");
});

test("header checkbox selects all rows and clears them", async ({ page }) => {
  await headerBox(page).check();
  await expect(selectedText(page)).toHaveText("7 selected");
  for (const name of NAMES) await expect(rowBox(page, name)).toBeChecked();
  expect(await isIndeterminate(page)).toBe(false);

  await headerBox(page).uncheck();
  await expect(selectedText(page)).toHaveText("0 selected");
  for (const name of NAMES) await expect(rowBox(page, name)).not.toBeChecked();
});

test("header checkbox is indeterminate while only some rows are selected", async ({ page }) => {
  expect(await isIndeterminate(page)).toBe(false);
  await rowBox(page, "draft.docx").check();
  await expect(selectedText(page)).toHaveText("1 selected");
  expect(await isIndeterminate(page)).toBe(true);
  await expect(headerBox(page)).not.toBeChecked();

  for (const name of NAMES) await rowBox(page, name).check();
  await expect(selectedText(page)).toHaveText("7 selected");
  expect(await isIndeterminate(page)).toBe(false);
  await expect(headerBox(page)).toBeChecked();

  await rowBox(page, "draft.docx").uncheck();
  expect(await isIndeterminate(page)).toBe(true);
});

test("delete asks for confirmation, removes rows and reports the count", async ({ page }) => {
  await rowBox(page, "contract.pdf").check();
  await rowBox(page, "photo.jpg").check();

  let message;
  page.once("dialog", (dialog) => {
    message = dialog.message();
    dialog.accept();
  });
  await page.getByRole("button", { name: "Delete selected" }).click();

  await expect(page.getByRole("status")).toContainText("2 files deleted");
  await expect(page.getByRole("button", { name: "Undo" })).toBeVisible();
  expect(message).toBe("Delete 2 files?");
  await expect(page.locator("#fm-rows tr")).toHaveCount(5);
  await expect(rowBox(page, "contract.pdf")).toHaveCount(0);
  await expect(rowBox(page, "photo.jpg")).toHaveCount(0);
  await expect(selectedText(page)).toHaveText("0 selected");

  await page.reload();
  await expect(page.locator("#fm-rows tr")).toHaveCount(5);
});

test("dismissing the confirm dialog deletes nothing", async ({ page }) => {
  await rowBox(page, "contract.pdf").check();
  await rowBox(page, "photo.jpg").check();

  let message;
  page.once("dialog", (dialog) => {
    message = dialog.message();
    dialog.dismiss();
  });
  await page.getByRole("button", { name: "Delete selected" }).click();

  await expect.poll(() => message).toBe("Delete 2 files?");
  await expect(page.locator("#fm-rows tr")).toHaveCount(7);
  await expect(page.getByRole("status")).toBeHidden();
  await expect(selectedText(page)).toHaveText("2 selected");

  await page.reload();
  await expect(page.locator("#fm-rows tr")).toHaveCount(7);
});

test("undo restores deleted files, including after a reload", async ({ page }) => {
  await headerBox(page).check();
  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "Delete selected" }).click();
  await expect(page.getByRole("status")).toContainText("7 files deleted");
  await expect(page.locator("#fm-rows tr")).toHaveCount(0);

  await page.getByRole("button", { name: "Undo" }).click();
  await expect(page.getByRole("status")).toBeHidden();
  await expect(page.locator("#fm-rows tr")).toHaveCount(7);

  await page.reload();
  await expect(page.locator("#fm-rows tr")).toHaveCount(7);
  for (const name of NAMES) await expect(page.getByRole("cell", { name, exact: true })).toBeVisible();
});
