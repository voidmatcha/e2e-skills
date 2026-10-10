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

const selectFile = async (page, name) => {
  await page.getByRole("checkbox", { name: `Select ${name}` }).check();
};

test.beforeEach(async ({ page, request }) => {
  await request.post("/api/reset");
  await page.goto("/");
});

test("lists seeded files and tracks row selection state", async ({ page }) => {
  for (const name of fileNames) {
    await expect(page.getByText(name, { exact: true })).toBeVisible();
  }

  const selectAll = page.getByRole("checkbox", { name: "Select all files" });
  await expect(page.getByText("0 selected")).toBeVisible();
  await expect(page.getByRole("button", { name: "Delete selected" })).toBeDisabled();
  await expect(selectAll).not.toBeChecked();
  await expect(selectAll).not.toHaveJSProperty("indeterminate", true);

  await selectFile(page, "budget.xlsx");
  await selectFile(page, "contract.pdf");

  await expect(page.getByText("2 selected")).toBeVisible();
  await expect(page.getByRole("button", { name: "Delete selected" })).toBeEnabled();
  await expect(selectAll).not.toBeChecked();
  await expect(selectAll).toHaveJSProperty("indeterminate", true);

  await selectAll.check();

  await expect(page.getByText("7 selected")).toBeVisible();
  await expect(selectAll).toBeChecked();
  await expect(selectAll).not.toHaveJSProperty("indeterminate", true);
  for (const name of fileNames) {
    await expect(page.getByRole("checkbox", { name: `Select ${name}` })).toBeChecked();
  }

  await selectAll.uncheck();

  await expect(page.getByText("0 selected")).toBeVisible();
  await expect(page.getByRole("button", { name: "Delete selected" })).toBeDisabled();
  await expect(selectAll).not.toBeChecked();
  await expect(selectAll).not.toHaveJSProperty("indeterminate", true);
  for (const name of fileNames) {
    await expect(page.getByRole("checkbox", { name: `Select ${name}` })).not.toBeChecked();
  }
});

test("dismisses delete confirmation without removing selected files", async ({ page }) => {
  await selectFile(page, "draft.docx");
  await selectFile(page, "logo.svg");
  await expect(page.getByText("2 selected")).toBeVisible();

  page.once("dialog", async (dialog) => {
    expect(dialog.message()).toBe("Delete 2 files?");
    await dialog.dismiss();
  });
  await page.getByRole("button", { name: "Delete selected" }).click();

  await expect(page.getByText("2 selected")).toBeVisible();
  await expect(page.getByText("2 files deleted")).toBeHidden();
  for (const name of fileNames) {
    await expect(page.getByText(name, { exact: true })).toBeVisible();
  }

  await page.reload();

  for (const name of fileNames) {
    await expect(page.getByText(name, { exact: true })).toBeVisible();
  }
});

test("deletes selected files and restores them with undo across reloads", async ({ page }) => {
  await selectFile(page, "budget.xlsx");
  await selectFile(page, "minutes.txt");
  await selectFile(page, "roadmap.md");

  page.once("dialog", async (dialog) => {
    expect(dialog.message()).toBe("Delete 3 files?");
    await dialog.accept();
  });
  await page.getByRole("button", { name: "Delete selected" }).click();

  await expect(page.getByText("3 files deleted")).toBeVisible();
  await expect(page.getByText("0 selected")).toBeVisible();
  await expect(page.getByText("budget.xlsx", { exact: true })).toBeHidden();
  await expect(page.getByText("minutes.txt", { exact: true })).toBeHidden();
  await expect(page.getByText("roadmap.md", { exact: true })).toBeHidden();
  await expect(page.getByText("contract.pdf", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: "Undo" }).click();

  await expect(page.getByText("3 files deleted")).toBeHidden();
  for (const name of fileNames) {
    await expect(page.getByText(name, { exact: true })).toBeVisible();
  }

  await page.reload();

  for (const name of fileNames) {
    await expect(page.getByText(name, { exact: true })).toBeVisible();
  }
});
