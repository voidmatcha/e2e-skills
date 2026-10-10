import { expect, test } from "@playwright/test";

const fileNames = [
  "budget.xlsx",
  "contract.pdf",
  "draft.docx",
  "logo.svg",
  "minutes.txt",
  "photo.jpg",
  "roadmap.md",
];

const rows = (page) => page.locator("#fm-rows tr");
const rowCheckbox = (page, name) => page.getByRole("checkbox", { name: `Select ${name}` });
const fileCell = (page, name) => page.getByRole("cell", { name, exact: true });
const selectAll = (page) => page.getByRole("checkbox", { name: "Select all files" });
const deleteSelected = (page) => page.getByRole("button", { name: "Delete selected" });

test.beforeEach(async ({ page, request }) => {
  await request.post("/api/reset");
  await page.goto("/");
});

test("shows seven seeded files with no selection", async ({ page }) => {
  await expect(rows(page)).toHaveCount(7);
  await expect(page.getByText("0 selected")).toBeVisible();
  await expect(deleteSelected(page)).toBeDisabled();

  for (const name of fileNames) {
    await expect(rowCheckbox(page, name)).toBeVisible();
    await expect(fileCell(page, name)).toBeVisible();
  }
});

test("selects rows individually and toggles all rows from the header checkbox", async ({ page }) => {
  await rowCheckbox(page, "budget.xlsx").check();

  await expect(page.getByText("1 selected")).toBeVisible();
  await expect(deleteSelected(page)).toBeEnabled();
  await expect(selectAll(page)).not.toBeChecked();
  await expect(selectAll(page)).toHaveJSProperty("indeterminate", true);

  await selectAll(page).check();

  await expect(page.getByText("7 selected")).toBeVisible();
  await expect(selectAll(page)).toBeChecked();
  await expect(selectAll(page)).toHaveJSProperty("indeterminate", false);
  for (const name of fileNames) {
    await expect(rowCheckbox(page, name)).toBeChecked();
  }

  await selectAll(page).uncheck();

  await expect(page.getByText("0 selected")).toBeVisible();
  await expect(deleteSelected(page)).toBeDisabled();
  await expect(selectAll(page)).not.toBeChecked();
  await expect(selectAll(page)).toHaveJSProperty("indeterminate", false);
  for (const name of fileNames) {
    await expect(rowCheckbox(page, name)).not.toBeChecked();
  }
});

test("does not delete files when the confirmation dialog is dismissed", async ({ page }) => {
  await rowCheckbox(page, "contract.pdf").check();
  await rowCheckbox(page, "logo.svg").check();

  page.once("dialog", async (dialog) => {
    expect(dialog.message()).toBe("Delete 2 files?");
    await dialog.dismiss();
  });
  await deleteSelected(page).click();

  await expect(rows(page)).toHaveCount(7);
  await expect(rowCheckbox(page, "contract.pdf")).toBeChecked();
  await expect(rowCheckbox(page, "logo.svg")).toBeChecked();
  await expect(page.getByRole("status")).toBeHidden();

  await page.reload();
  await expect(rows(page)).toHaveCount(7);
  for (const name of fileNames) {
    await expect(fileCell(page, name)).toBeVisible();
  }
});

test("deletes confirmed files and restores them with undo after reload", async ({ page, request }) => {
  const deletedNames = ["budget.xlsx", "draft.docx", "roadmap.md"];

  for (const name of deletedNames) {
    await rowCheckbox(page, name).check();
  }

  page.once("dialog", async (dialog) => {
    expect(dialog.message()).toBe("Delete 3 files?");
    await dialog.accept();
  });
  await deleteSelected(page).click();

  await expect(rows(page)).toHaveCount(4);
  await expect(page.getByRole("status")).toContainText("3 files deleted");
  await expect(page.getByText("0 selected")).toBeVisible();
  for (const name of deletedNames) {
    await expect(fileCell(page, name)).toBeHidden();
  }

  const filesAfterDelete = await request.get("/api/files");
  expect((await filesAfterDelete.json()).filter((file) => file.deleted).map((file) => file.name)).toEqual(deletedNames);

  await page.getByRole("button", { name: "Undo" }).click();

  await expect(rows(page)).toHaveCount(7);
  for (const name of fileNames) {
    await expect(fileCell(page, name)).toBeVisible();
  }

  await page.reload();
  await expect(rows(page)).toHaveCount(7);
  for (const name of fileNames) {
    await expect(fileCell(page, name)).toBeVisible();
  }
});
