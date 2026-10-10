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

test.beforeEach(async ({ page }) => {
  await page.request.post("/api/reset");
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Files", exact: true })).toBeVisible();
});

test("shows seven seeded files with no selection", async ({ page }) => {
  await expect(page.getByText("0 selected")).toBeVisible();
  await expect(page.getByRole("button", { name: "Delete selected", exact: true })).toBeDisabled();

  for (const name of fileNames) {
    await expect(page.getByRole("cell", { name, exact: true })).toBeVisible();
    await expect(page.getByRole("checkbox", { name: `Select ${name}`, exact: true })).not.toBeChecked();
  }
});

test("updates header selection between mixed, selected, and cleared states", async ({ page }) => {
  const selectAll = page.getByRole("checkbox", { name: "Select all files", exact: true });

  await page.getByRole("checkbox", { name: "Select budget.xlsx", exact: true }).check();

  await expect(page.getByText("1 selected")).toBeVisible();
  await expect(selectAll).toHaveJSProperty("indeterminate", true);

  await selectAll.check();

  await expect(page.getByText("7 selected")).toBeVisible();
  await expect(selectAll).toBeChecked();

  await selectAll.uncheck();

  await expect(page.getByText("0 selected")).toBeVisible();
  await expect(selectAll).not.toBeChecked();
  await expect(selectAll).toHaveJSProperty("indeterminate", false);
  for (const name of fileNames) {
    await expect(page.getByRole("checkbox", { name: `Select ${name}`, exact: true })).not.toBeChecked();
  }
});

test("keeps selected files when delete is dismissed", async ({ page }) => {
  await page.getByRole("checkbox", { name: "Select budget.xlsx", exact: true }).check();
  await page.getByRole("checkbox", { name: "Select contract.pdf", exact: true }).check();

  page.once("dialog", async (dialog) => {
    expect(dialog.message()).toBe("Delete 2 files?");
    await dialog.dismiss();
  });

  await page.getByRole("button", { name: "Delete selected", exact: true }).click();

  await expect(page.getByText("2 selected")).toBeVisible();
  for (const name of fileNames) {
    await expect(page.getByRole("cell", { name, exact: true })).toBeVisible();
  }
});

test("deletes selected files and undo restores them after reload", async ({ page }) => {
  const budgetCell = page.getByRole("cell", { name: "budget.xlsx", exact: true });
  const contractCell = page.getByRole("cell", { name: "contract.pdf", exact: true });

  await page.getByRole("checkbox", { name: "Select budget.xlsx", exact: true }).check();
  await page.getByRole("checkbox", { name: "Select contract.pdf", exact: true }).check();
  await expect(budgetCell).toBeVisible();
  await expect(contractCell).toBeVisible();

  page.once("dialog", async (dialog) => {
    expect(dialog.message()).toBe("Delete 2 files?");
    await dialog.accept();
  });
  const deleteRequest = page.waitForRequest((request) => (
    request.method() === "POST" && request.url().endsWith("/api/files/delete")
  ));

  await page.getByRole("button", { name: "Delete selected", exact: true }).click();
  await deleteRequest;

  await expect(page.getByText("2 files deleted")).toBeVisible();
  await expect(budgetCell).toHaveCount(0);
  await expect(contractCell).toHaveCount(0);

  const restoreRequest = page.waitForRequest((request) => (
    request.method() === "POST" && request.url().endsWith("/api/files/restore")
  ));

  await page.getByRole("button", { name: "Undo", exact: true }).click();
  await restoreRequest;

  await expect(budgetCell).toBeVisible();
  await expect(contractCell).toBeVisible();

  await page.reload();

  await expect(budgetCell).toBeVisible();
  await expect(contractCell).toBeVisible();
});
