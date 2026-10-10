import { expect, test } from "@playwright/test";

const NAMES = ["budget.xlsx", "contract.pdf", "draft.docx", "logo.svg", "minutes.txt", "photo.jpg", "roadmap.md"];

test.beforeEach(async ({ page, request }) => {
  const res = await request.post("/api/reset");
  expect(res.ok()).toBeTruthy();
  await page.goto("/");
  await expect(page.locator("#fm-rows tr")).toHaveCount(NAMES.length);
});

const rowBox = (page, name) => page.getByRole("checkbox", { name: `Select ${name}` });
const selectAll = (page) => page.getByRole("checkbox", { name: "Select all files" });
const status = (page) => page.locator("#fm-selected");
const deleteButton = (page) => page.getByRole("button", { name: "Delete selected" });

test("lists the seven seeded files with nothing selected", async ({ page }) => {
  for (const name of NAMES) await expect(page.getByRole("cell", { name, exact: true })).toBeVisible();
  await expect(status(page)).toHaveText("0 selected");
  await expect(deleteButton(page)).toBeDisabled();
  await expect(selectAll(page)).not.toBeChecked();
});

test("selecting rows updates the count and the header indeterminate state", async ({ page }) => {
  await rowBox(page, "budget.xlsx").check();
  await expect(status(page)).toHaveText("1 selected");
  await expect(selectAll(page)).toHaveJSProperty("indeterminate", true);
  await expect(deleteButton(page)).toBeEnabled();

  await rowBox(page, "logo.svg").check();
  await expect(status(page)).toHaveText("2 selected");

  await rowBox(page, "budget.xlsx").uncheck();
  await rowBox(page, "logo.svg").uncheck();
  await expect(status(page)).toHaveText("0 selected");
  await expect(selectAll(page)).toHaveJSProperty("indeterminate", false);
  await expect(selectAll(page)).not.toBeChecked();
});

test("header checkbox selects every row and clears them all", async ({ page }) => {
  await selectAll(page).check();
  await expect(status(page)).toHaveText("7 selected");
  await expect(selectAll(page)).toBeChecked();
  await expect(selectAll(page)).toHaveJSProperty("indeterminate", false);
  for (const name of NAMES) await expect(rowBox(page, name)).toBeChecked();

  await selectAll(page).uncheck();
  await expect(status(page)).toHaveText("0 selected");
  for (const name of NAMES) await expect(rowBox(page, name)).not.toBeChecked();
});

test("header checkbox selects the rest when only some are selected", async ({ page }) => {
  await rowBox(page, "photo.jpg").check();
  await expect(selectAll(page)).toHaveJSProperty("indeterminate", true);
  await selectAll(page).click();
  await expect(status(page)).toHaveText("7 selected");
  await expect(selectAll(page)).toBeChecked();
});

test("selecting all rows individually checks the header", async ({ page }) => {
  for (const name of NAMES) await rowBox(page, name).check();
  await expect(status(page)).toHaveText("7 selected");
  await expect(selectAll(page)).toBeChecked();
  await expect(selectAll(page)).toHaveJSProperty("indeterminate", false);
});

test("dismissing the delete confirmation deletes nothing", async ({ page }) => {
  await rowBox(page, "budget.xlsx").check();
  await rowBox(page, "contract.pdf").check();

  const messages = [];
  page.once("dialog", (dialog) => {
    messages.push(dialog.message());
    return dialog.dismiss();
  });
  await deleteButton(page).click();

  await expect.poll(() => messages).toEqual(["Delete 2 files?"]);
  await expect(page.locator("#fm-rows tr")).toHaveCount(7);
  await expect(page.locator("#fm-toast")).toBeHidden();
  await expect(status(page)).toHaveText("2 selected");

  await page.reload();
  await expect(page.locator("#fm-rows tr")).toHaveCount(7);
});

test("confirming deletes the selected rows and shows the toast", async ({ page }) => {
  await rowBox(page, "budget.xlsx").check();
  await rowBox(page, "draft.docx").check();
  await rowBox(page, "roadmap.md").check();

  const messages = [];
  page.once("dialog", (dialog) => {
    messages.push(dialog.message());
    return dialog.accept();
  });
  await deleteButton(page).click();

  await expect.poll(() => messages).toEqual(["Delete 3 files?"]);
  await expect(page.locator("#fm-toast")).toBeVisible();
  await expect(page.locator("#fm-toast")).toContainText("3 files deleted");
  await expect(page.getByRole("button", { name: "Undo" })).toBeVisible();
  await expect(page.locator("#fm-rows tr")).toHaveCount(4);
  for (const name of ["budget.xlsx", "draft.docx", "roadmap.md"]) {
    await expect(page.getByRole("cell", { name, exact: true })).toHaveCount(0);
  }
  for (const name of ["contract.pdf", "logo.svg", "minutes.txt", "photo.jpg"]) {
    await expect(page.getByRole("cell", { name, exact: true })).toBeVisible();
  }
  await expect(status(page)).toHaveText("0 selected");

  await page.reload();
  await expect(page.locator("#fm-rows tr")).toHaveCount(4);
});

test("undo restores the deleted files, including after a reload", async ({ page }) => {
  await rowBox(page, "logo.svg").check();
  await rowBox(page, "minutes.txt").check();
  page.once("dialog", (dialog) => dialog.accept());
  await deleteButton(page).click();
  await expect(page.locator("#fm-toast")).toContainText("2 files deleted");
  await expect(page.locator("#fm-rows tr")).toHaveCount(5);

  await page.getByRole("button", { name: "Undo" }).click();
  await expect(page.locator("#fm-toast")).toBeHidden();
  await expect(page.locator("#fm-rows tr")).toHaveCount(7);
  await expect(page.getByRole("cell", { name: "logo.svg", exact: true })).toBeVisible();
  await expect(page.getByRole("cell", { name: "minutes.txt", exact: true })).toBeVisible();

  await page.reload();
  await expect(page.locator("#fm-rows tr")).toHaveCount(7);
  for (const name of NAMES) await expect(page.getByRole("cell", { name, exact: true })).toBeVisible();
});

test("deleting everything via select all and undoing restores all rows", async ({ page }) => {
  await selectAll(page).check();
  page.once("dialog", (dialog) => dialog.accept());
  await deleteButton(page).click();
  await expect(page.locator("#fm-toast")).toContainText("7 files deleted");
  await expect(page.locator("#fm-rows tr")).toHaveCount(0);
  await expect(selectAll(page)).not.toBeChecked();

  await page.getByRole("button", { name: "Undo" }).click();
  await page.reload();
  await expect(page.locator("#fm-rows tr")).toHaveCount(7);
});
