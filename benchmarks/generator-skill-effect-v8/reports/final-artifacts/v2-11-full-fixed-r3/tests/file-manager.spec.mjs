import { expect, test } from "@playwright/test";

const files = [
  "budget.xlsx",
  "contract.pdf",
  "draft.docx",
  "logo.svg",
  "minutes.txt",
  "photo.jpg",
  "roadmap.md",
];

test.beforeEach(async ({ page, request }) => {
  await request.post("/api/reset");
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Files", exact: true })).toBeVisible();
  await expect(page.getByRole("row")).toHaveCount(files.length + 1);
});

test("updates row and header selection state", async ({ page }) => {
  const selectAll = page.getByRole("checkbox", { name: "Select all files", exact: true });
  const deleteButton = page.getByRole("button", { name: "Delete selected", exact: true });

  await expect(page.getByText("0 selected")).toBeVisible();
  await expect(deleteButton).toBeDisabled();

  await page.getByRole("checkbox", { name: "Select budget.xlsx", exact: true }).check();

  await expect(page.getByText("1 selected")).toBeVisible();
  await expect(deleteButton).toBeEnabled();
  await expect(selectAll).not.toBeChecked();
  await expect(selectAll).toHaveJSProperty("indeterminate", true);

  await selectAll.check();

  await expect(page.getByText("7 selected")).toBeVisible();
  await expect(selectAll).toBeChecked();
  for (const file of files) {
    await expect(page.getByRole("checkbox", { name: `Select ${file}`, exact: true })).toBeChecked();
  }

  await selectAll.uncheck();

  await expect(page.getByText("0 selected")).toBeVisible();
  await expect(deleteButton).toBeDisabled();
  await expect(selectAll).not.toBeChecked();
  await expect(selectAll).toHaveJSProperty("indeterminate", false);
  for (const file of files) {
    await expect(page.getByRole("checkbox", { name: `Select ${file}`, exact: true })).not.toBeChecked();
  }
});

test("keeps files when the delete confirmation is dismissed", async ({ page }) => {
  await page.getByRole("checkbox", { name: "Select budget.xlsx", exact: true }).check();
  await page.getByRole("checkbox", { name: "Select contract.pdf", exact: true }).check();

  page.once("dialog", async (dialog) => {
    expect(dialog.message()).toBe("Delete 2 files?");
    await dialog.dismiss();
  });
  await page.getByRole("button", { name: "Delete selected", exact: true }).click();

  await expect(page.getByText("2 selected")).toBeVisible();
  await expect(page.getByRole("row")).toHaveCount(files.length + 1);

  await page.reload();

  await expect(page.getByRole("row")).toHaveCount(files.length + 1);
  await expect(page.getByText("0 selected")).toBeVisible();
  for (const file of files) {
    await expect(page.getByRole("cell", { name: file, exact: true })).toBeVisible();
  }
});

test("deletes selected files and restores them with undo after reload", async ({ page }) => {
  await expect(page.getByRole("cell", { name: "budget.xlsx", exact: true })).toBeVisible();
  await expect(page.getByRole("cell", { name: "contract.pdf", exact: true })).toBeVisible();
  await expect(page.getByRole("cell", { name: "draft.docx", exact: true })).toBeVisible();

  await page.getByRole("checkbox", { name: "Select budget.xlsx", exact: true }).check();
  await page.getByRole("checkbox", { name: "Select contract.pdf", exact: true }).check();
  await page.getByRole("checkbox", { name: "Select draft.docx", exact: true }).check();

  page.once("dialog", async (dialog) => {
    expect(dialog.message()).toBe("Delete 3 files?");
    await dialog.accept();
  });
  const deleteRequest = page.waitForRequest((request) => {
    return request.method() === "POST" && new URL(request.url()).pathname === "/api/files/delete";
  });
  await page.getByRole("button", { name: "Delete selected", exact: true }).click();
  const deleted = await deleteRequest;
  const deleteResponse = await deleted.response();

  expect(deleted.postDataJSON()).toEqual({ ids: [1, 2, 3] });
  expect(deleteResponse?.status()).toBe(200);
  await expect(page.getByRole("status")).toContainText("3 files deleted");
  await expect(page.getByText("0 selected")).toBeVisible();
  await expect(page.getByRole("row")).toHaveCount(files.length - 3 + 1);
  await expect(page.getByRole("cell", { name: "budget.xlsx", exact: true })).toHaveCount(0);
  await expect(page.getByRole("cell", { name: "contract.pdf", exact: true })).toHaveCount(0);
  await expect(page.getByRole("cell", { name: "draft.docx", exact: true })).toHaveCount(0);

  const restoreRequest = page.waitForRequest((request) => {
    return request.method() === "POST" && new URL(request.url()).pathname === "/api/files/restore";
  });
  await page.getByRole("button", { name: "Undo", exact: true }).click();
  const restored = await restoreRequest;
  const restoreResponse = await restored.response();

  expect(restored.postDataJSON()).toEqual({ ids: [1, 2, 3] });
  expect(restoreResponse?.status()).toBe(200);
  await expect(page.getByRole("status")).toBeHidden();
  await expect(page.getByRole("row")).toHaveCount(files.length + 1);

  await page.reload();

  await expect(page.getByRole("row")).toHaveCount(files.length + 1);
  for (const file of files) {
    await expect(page.getByRole("cell", { name: file, exact: true })).toBeVisible();
  }
});
