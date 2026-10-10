import { expect, test } from "@playwright/test";

const fileNames = ["budget.xlsx", "contract.pdf", "draft.docx", "logo.svg", "minutes.txt", "photo.jpg", "roadmap.md"];

test.beforeEach(async ({ request }) => {
  await request.post("/api/reset");
});

const rowCheckbox = (page, name) => page.getByRole("checkbox", { name: `Select ${name}` });

test("selects individual files and toggles all files from the header", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByRole("row")).toHaveCount(fileNames.length + 1);
  await expect(page.getByText("0 selected")).toBeVisible();

  const selectAll = page.getByRole("checkbox", { name: "Select all files" });
  await rowCheckbox(page, "budget.xlsx").check();
  await rowCheckbox(page, "contract.pdf").check();

  await expect(page.getByText("2 selected")).toBeVisible();
  await expect(selectAll).not.toBeChecked();
  await expect(selectAll).toHaveJSProperty("indeterminate", true);

  await selectAll.check();
  await expect(page.getByText("7 selected")).toBeVisible();
  await expect(selectAll).toBeChecked();
  await expect(selectAll).toHaveJSProperty("indeterminate", false);
  for (const name of fileNames) {
    await expect(rowCheckbox(page, name)).toBeChecked();
  }

  await selectAll.uncheck();
  await expect(page.getByText("0 selected")).toBeVisible();
  await expect(selectAll).not.toBeChecked();
  await expect(selectAll).toHaveJSProperty("indeterminate", false);
  for (const name of fileNames) {
    await expect(rowCheckbox(page, name)).not.toBeChecked();
  }
});

test("keeps files when delete is dismissed", async ({ page }) => {
  await page.goto("/");

  await rowCheckbox(page, "draft.docx").check();
  await rowCheckbox(page, "logo.svg").check();

  page.once("dialog", async (dialog) => {
    expect(dialog.message()).toBe("Delete 2 files?");
    await dialog.dismiss();
  });
  await page.getByRole("button", { name: "Delete selected" }).click();

  await expect(page.getByText("2 selected")).toBeVisible();
  await expect(page.getByText("2 files deleted")).toBeHidden();
  await expect(page.getByRole("row")).toHaveCount(fileNames.length + 1);
  await expect(rowCheckbox(page, "draft.docx")).toBeChecked();
  await expect(rowCheckbox(page, "logo.svg")).toBeChecked();
});

test("deletes selected files and restores them with undo", async ({ page }) => {
  await page.goto("/");

  await rowCheckbox(page, "minutes.txt").check();
  await rowCheckbox(page, "photo.jpg").check();
  await rowCheckbox(page, "roadmap.md").check();

  page.once("dialog", async (dialog) => {
    expect(dialog.message()).toBe("Delete 3 files?");
    await dialog.accept();
  });
  await page.getByRole("button", { name: "Delete selected" }).click();

  await expect(page.getByText("3 files deleted")).toBeVisible();
  await expect(page.getByText("0 selected")).toBeVisible();
  await expect(page.getByRole("row")).toHaveCount(fileNames.length - 3 + 1);
  for (const name of ["minutes.txt", "photo.jpg", "roadmap.md"]) {
    await expect(page.getByText(name)).toBeHidden();
  }

  await page.getByRole("button", { name: "Undo" }).click();

  await expect(page.getByText("3 files deleted")).toBeHidden();
  await expect(page.getByRole("row")).toHaveCount(fileNames.length + 1);
  for (const name of fileNames) {
    await expect(page.getByText(name)).toBeVisible();
  }

  await page.reload();
  await expect(page.getByRole("row")).toHaveCount(fileNames.length + 1);
  for (const name of fileNames) {
    await expect(page.getByText(name)).toBeVisible();
  }
});
