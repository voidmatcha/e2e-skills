import { expect, test } from "@playwright/test";

const resetNotes = async (request) => {
  const response = await request.post("/api/reset");
  if (!response.ok()) {
    throw new Error(`Failed to reset notes: ${response.status()}`);
  }
};

const noteItem = (list, title) => list.getByRole("listitem").filter({ hasText: title });

test.beforeEach(async ({ request }) => {
  await resetNotes(request);
});

test("moves a deleted note to Trash and persists after reload", async ({ page }) => {
  await page.goto("/");

  const notesTab = page.getByRole("tab", { name: "Notes", exact: true });
  const trashTab = page.getByRole("tab", { name: /^Trash \(1\)$/ });
  const notesList = page.getByRole("list", { name: "Notes", exact: true });
  const trashList = page.getByRole("list", { name: "Trash", exact: true });
  const groceryNote = noteItem(notesList, "Grocery list");

  await expect(notesTab).toHaveAttribute("aria-selected", "true");
  await expect(notesList.getByRole("listitem")).toHaveCount(3);

  const trashRequest = page.waitForRequest(
    (request) => request.method() === "POST" && request.url().endsWith("/api/notes/1/trash"),
  );
  await groceryNote.getByRole("button", { name: "Delete Grocery list", exact: true }).click();
  await trashRequest;

  await expect(page.getByRole("tab", { name: /^Trash \(2\)$/ })).toBeVisible();
  await expect(groceryNote).toHaveCount(0);

  await page.getByRole("tab", { name: /^Trash \(2\)$/ }).click();
  await expect(noteItem(trashList, "Grocery list")).toHaveCount(1);

  await page.reload();
  await page.getByRole("tab", { name: /^Trash \(2\)$/ }).click();
  await expect(noteItem(trashList, "Grocery list")).toHaveCount(1);

  await page.getByRole("tab", { name: "Notes", exact: true }).click();
  await expect(noteItem(notesList, "Grocery list")).toHaveCount(0);
});

test("restores a trashed note to Notes and persists after reload", async ({ page }) => {
  await page.goto("/");

  const notesList = page.getByRole("list", { name: "Notes", exact: true });
  const trashList = page.getByRole("list", { name: "Trash", exact: true });

  await page.getByRole("tab", { name: /^Trash \(1\)$/ }).click();
  await expect(noteItem(trashList, "Old draft")).toBeVisible();

  const restoreRequest = page.waitForRequest(
    (request) => request.method() === "POST" && request.url().endsWith("/api/notes/4/restore"),
  );
  await noteItem(trashList, "Old draft").getByRole("button", { name: "Restore Old draft", exact: true }).click();
  await restoreRequest;

  await expect(page.getByRole("tab", { name: /^Trash \(0\)$/ })).toBeVisible();
  await expect(noteItem(trashList, "Old draft")).toHaveCount(0);

  await page.getByRole("tab", { name: "Notes", exact: true }).click();
  await expect(noteItem(notesList, "Old draft")).toHaveCount(1);

  await page.reload();
  await expect(noteItem(notesList, "Old draft")).toHaveCount(1);

  await page.getByRole("tab", { name: /^Trash \(0\)$/ }).click();
  await expect(noteItem(trashList, "Old draft")).toHaveCount(0);
});

test("empties Trash after confirmation and persists after reload", async ({ page }) => {
  await page.goto("/");

  const trashList = page.getByRole("list", { name: "Trash", exact: true });

  await page.getByRole("tab", { name: /^Trash \(1\)$/ }).click();
  await expect(noteItem(trashList, "Old draft")).toBeVisible();

  page.once("dialog", async (dialog) => {
    expect(dialog.message()).toBe("Permanently delete everything in the Trash?");
    await dialog.accept();
  });

  const emptyRequest = page.waitForRequest(
    (request) => request.method() === "POST" && request.url().endsWith("/api/trash/empty"),
  );
  await page.getByRole("button", { name: "Empty trash", exact: true }).click();
  await emptyRequest;

  await expect(page.getByText("Trash is empty")).toBeVisible();
  await expect(page.getByRole("tab", { name: /^Trash \(0\)$/ })).toBeVisible();

  await page.reload();
  await page.getByRole("tab", { name: /^Trash \(0\)$/ }).click();
  await expect(page.getByText("Trash is empty")).toBeVisible();
});
