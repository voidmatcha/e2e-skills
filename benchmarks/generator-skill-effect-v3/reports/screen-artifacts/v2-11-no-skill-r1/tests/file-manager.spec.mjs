import { expect, test } from "@playwright/test";

const NAMES = ["budget.xlsx", "contract.pdf", "draft.docx", "logo.svg", "minutes.txt", "photo.jpg", "roadmap.md"];

test.beforeEach(async ({ page, request }) => {
  await request.post("/api/reset");
  await page.goto("/");
  await expect(page.getByRole("row")).toHaveCount(NAMES.length + 1);
});

const rowBox = (page, name) => page.getByRole("checkbox", { name: `Select ${name}` });
const selectAll = (page) => page.getByRole("checkbox", { name: "Select all files" });
const isIndeterminate = (page) => selectAll(page).evaluate((el) => el.indeterminate);

test("lists the seven seeded files with nothing selected", async ({ page }) => {
  for (const name of NAMES) await expect(page.getByRole("cell", { name, exact: true })).toBeVisible();
  await expect(page.getByText("0 selected")).toBeVisible();
  await expect(page.getByRole("button", { name: "Delete selected" })).toBeDisabled();
});

test("selecting rows updates the count and the header indeterminate state", async ({ page }) => {
  await rowBox(page, "budget.xlsx").check();
  await rowBox(page, "logo.svg").check();
  await expect(page.getByText("2 selected")).toBeVisible();
  await expect(selectAll(page)).not.toBeChecked();
  expect(await isIndeterminate(page)).toBe(true);
  await expect(page.getByRole("button", { name: "Delete selected" })).toBeEnabled();

  await rowBox(page, "logo.svg").uncheck();
  await expect(page.getByText("1 selected")).toBeVisible();
});

test("header checkbox selects all rows and clears them", async ({ page }) => {
  await selectAll(page).check();
  await expect(page.getByText("7 selected")).toBeVisible();
  for (const name of NAMES) await expect(rowBox(page, name)).toBeChecked();
  await expect(selectAll(page)).toBeChecked();
  expect(await isIndeterminate(page)).toBe(false);

  await selectAll(page).uncheck();
  await expect(page.getByText("0 selected")).toBeVisible();
  for (const name of NAMES) await expect(rowBox(page, name)).not.toBeChecked();
});

test("selecting every row individually checks the header", async ({ page }) => {
  for (const name of NAMES) await rowBox(page, name).check();
  await expect(selectAll(page)).toBeChecked();
  expect(await isIndeterminate(page)).toBe(false);
});

test("header checkbox from a partial selection selects all", async ({ page }) => {
  await rowBox(page, "draft.docx").check();
  await selectAll(page).check();
  await expect(page.getByText("7 selected")).toBeVisible();
});

test("confirming delete removes the rows and shows the toast", async ({ page }) => {
  await rowBox(page, "contract.pdf").check();
  await rowBox(page, "photo.jpg").check();

  let message;
  page.once("dialog", (dialog) => {
    message = dialog.message();
    return dialog.accept();
  });
  await page.getByRole("button", { name: "Delete selected" }).click();

  await expect(page.getByText("2 files deleted")).toBeVisible();
  expect(message).toBe("Delete 2 files?");
  await expect(page.getByRole("button", { name: "Undo" })).toBeVisible();
  await expect(page.getByRole("cell", { name: "contract.pdf", exact: true })).toHaveCount(0);
  await expect(page.getByRole("cell", { name: "photo.jpg", exact: true })).toHaveCount(0);
  await expect(page.getByRole("row")).toHaveCount(6);
  await expect(page.getByText("0 selected")).toBeVisible();
});

test("dismissing the dialog deletes nothing", async ({ page }) => {
  await rowBox(page, "contract.pdf").check();
  await rowBox(page, "photo.jpg").check();

  let message;
  page.once("dialog", (dialog) => {
    message = dialog.message();
    return dialog.dismiss();
  });
  await page.getByRole("button", { name: "Delete selected" }).click();

  await expect.poll(() => message).toBe("Delete 2 files?");
  await expect(page.getByRole("row")).toHaveCount(NAMES.length + 1);
  await expect(page.getByText("2 selected")).toBeVisible();
  await expect(page.getByText(/files deleted/)).toBeHidden();

  await page.reload();
  await expect(page.getByRole("row")).toHaveCount(NAMES.length + 1);
});

test("undo restores deleted files, including after a reload", async ({ page }) => {
  await rowBox(page, "contract.pdf").check();
  await rowBox(page, "photo.jpg").check();
  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "Delete selected" }).click();
  await expect(page.getByText("2 files deleted")).toBeVisible();

  await page.getByRole("button", { name: "Undo" }).click();
  await expect(page.getByText("2 files deleted")).toBeHidden();
  await expect(page.getByRole("row")).toHaveCount(NAMES.length + 1);
  await expect(page.getByRole("cell", { name: "contract.pdf", exact: true })).toBeVisible();

  await page.reload();
  await expect(page.getByRole("row")).toHaveCount(NAMES.length + 1);
  for (const name of NAMES) await expect(page.getByRole("cell", { name, exact: true })).toBeVisible();
});

test("deleted files stay gone after a reload", async ({ page }) => {
  await selectAll(page).check();
  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "Delete selected" }).click();
  await expect(page.getByText("7 files deleted")).toBeVisible();
  await expect(page.getByRole("row")).toHaveCount(1);

  await page.reload();
  await expect(page.getByRole("row")).toHaveCount(1);
});
