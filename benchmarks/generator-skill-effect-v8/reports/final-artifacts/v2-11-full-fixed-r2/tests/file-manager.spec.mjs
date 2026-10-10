import { expect, test } from "@playwright/test";

const seededFiles = [
  "budget.xlsx",
  "contract.pdf",
  "draft.docx",
  "logo.svg",
  "minutes.txt",
  "photo.jpg",
  "roadmap.md",
];

const fileRows = (page) => page.locator("tbody").getByRole("row");

const deletedStateFor = async (request, names) => {
  const response = await request.get("/api/files");
  const files = await response.json();
  return Object.fromEntries(
    files.filter((file) => names.includes(file.name)).map((file) => [file.name, file.deleted]),
  );
};

test.beforeEach(async ({ page, request }) => {
  await request.post("/api/reset");
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Files" })).toBeVisible();
  await expect(fileRows(page)).toHaveCount(seededFiles.length);
});

test("updates the selected count and header checkbox state for row selections", async ({ page }) => {
  const selectAll = page.getByRole("checkbox", { name: "Select all files" });

  await page.getByRole("checkbox", { name: "Select budget.xlsx" }).check();
  await page.getByRole("checkbox", { name: "Select contract.pdf" }).check();

  await expect(page.getByText("2 selected")).toBeVisible();
  await expect(selectAll).not.toBeChecked();
  await expect(selectAll).toHaveJSProperty("indeterminate", true);

  await page.getByRole("checkbox", { name: "Select budget.xlsx" }).uncheck();

  await expect(page.getByText("1 selected")).toBeVisible();
  await expect(selectAll).toHaveJSProperty("indeterminate", true);

  await page.getByRole("checkbox", { name: "Select contract.pdf" }).uncheck();

  await expect(page.getByText("0 selected")).toBeVisible();
  await expect(selectAll).not.toBeChecked();
  await expect(selectAll).toHaveJSProperty("indeterminate", false);
});

test("selects every row and clears every row from the header checkbox", async ({ page }) => {
  const selectAll = page.getByRole("checkbox", { name: "Select all files" });

  await selectAll.check();

  await expect(page.getByText(`${seededFiles.length} selected`)).toBeVisible();
  await expect(selectAll).toBeChecked();
  for (const name of seededFiles) {
    await expect(page.getByRole("checkbox", { name: `Select ${name}` })).toBeChecked();
  }

  await selectAll.uncheck();

  await expect(page.getByText("0 selected")).toBeVisible();
  await expect(selectAll).not.toBeChecked();
  for (const name of seededFiles) {
    await expect(page.getByRole("checkbox", { name: `Select ${name}` })).not.toBeChecked();
  }
});

test("keeps files when the delete dialog is dismissed", async ({ page }) => {
  await page.getByRole("checkbox", { name: "Select budget.xlsx" }).check();
  await page.getByRole("checkbox", { name: "Select contract.pdf" }).check();

  page.once("dialog", async (dialog) => {
    expect(dialog.message()).toBe("Delete 2 files?");
    await dialog.dismiss();
  });
  await page.getByRole("button", { name: "Delete selected" }).click();

  await expect(fileRows(page)).toHaveCount(seededFiles.length);
  await expect(page.getByRole("checkbox", { name: "Select budget.xlsx" })).toBeVisible();
  await expect(page.getByRole("checkbox", { name: "Select contract.pdf" })).toBeVisible();
  await expect(page.getByText("2 selected")).toBeVisible();
});

test("deletes selected files and undo restores them after reload", async ({ page, request }) => {
  await page.getByRole("checkbox", { name: "Select budget.xlsx" }).check();
  await page.getByRole("checkbox", { name: "Select contract.pdf" }).check();

  const deleteRequest = page.waitForRequest((request) => {
    if (!request.url().endsWith("/api/files/delete") || request.method() !== "POST") return false;
    const body = request.postDataJSON();
    return JSON.stringify(body) === JSON.stringify({ ids: [1, 2] });
  });
  page.once("dialog", async (dialog) => {
    expect(dialog.message()).toBe("Delete 2 files?");
    await dialog.accept();
  });
  await page.getByRole("button", { name: "Delete selected" }).click();
  await deleteRequest;

  await expect
    .poll(() => deletedStateFor(request, ["budget.xlsx", "contract.pdf"]))
    .toEqual({ "budget.xlsx": true, "contract.pdf": true });
  await expect(page.getByText("2 files deleted")).toBeVisible();
  await expect(fileRows(page)).toHaveCount(seededFiles.length - 2);
  await expect(page.getByRole("checkbox", { name: "Select budget.xlsx" })).toHaveCount(0);
  await expect(page.getByRole("checkbox", { name: "Select contract.pdf" })).toHaveCount(0);

  const restoreRequest = page.waitForRequest((request) => {
    if (!request.url().endsWith("/api/files/restore") || request.method() !== "POST") return false;
    const body = request.postDataJSON();
    return JSON.stringify(body) === JSON.stringify({ ids: [1, 2] });
  });
  await page.getByRole("button", { name: "Undo" }).click();
  await restoreRequest;

  await expect
    .poll(() => deletedStateFor(request, ["budget.xlsx", "contract.pdf"]))
    .toEqual({ "budget.xlsx": false, "contract.pdf": false });
  await expect(fileRows(page)).toHaveCount(seededFiles.length);
  await page.reload();
  await expect(fileRows(page)).toHaveCount(seededFiles.length);
  await expect(page.getByRole("checkbox", { name: "Select budget.xlsx" })).toBeVisible();
  await expect(page.getByRole("checkbox", { name: "Select contract.pdf" })).toBeVisible();
});
