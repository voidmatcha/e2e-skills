import { expect, test } from "@playwright/test";

const noteTitles = ["Grocery list", "Meeting notes", "Gift ideas"];
const trashedTitle = "Old draft";

test.beforeEach(async ({ page, request }) => {
  const reset = await request.post("/api/reset");
  if (!reset.ok()) throw new Error("Failed to reset seeded notes");
  await page.goto("/");
});

test("shows seeded notes separately from the Trash view", async ({ page }) => {
  const notesList = page.getByRole("list", { name: /^Notes$/ });
  const trashTab = page.getByRole("tab", { name: /^Trash \(1\)$/ });

  await expect(notesList.getByRole("listitem")).toHaveCount(3);
  await expect(notesList.getByRole("listitem")).toContainText(noteTitles);
  await expect(notesList).not.toContainText(trashedTitle);
  await expect(trashTab).toBeVisible();

  await trashTab.click();

  const trashList = page.getByRole("list", { name: /^Trash$/ });
  await expect(trashList.getByRole("listitem")).toHaveCount(1);
  await expect(trashList).toContainText(trashedTitle);
  for (const title of noteTitles) {
    await expect(trashList).not.toContainText(title);
  }
});

test("moves a deleted note to Trash and keeps it there after reload", async ({ page }) => {
  const notesList = page.getByRole("list", { name: /^Notes$/ });
  const trashTab = page.getByRole("tab", { name: /^Trash \(\d+\)$/ });
  const deletedNote = notesList.getByRole("listitem").filter({ hasText: "Grocery list" });
  const trashRequest = page.waitForRequest(
    (request) =>
      request.method() === "POST" &&
      new URL(request.url()).pathname === "/api/notes/1/trash",
  );

  await deletedNote.getByRole("button", { name: "Delete Grocery list" }).click();
  await trashRequest;

  await expect(notesList).not.toContainText("Grocery list");
  await expect(trashTab).toHaveText("Trash (2)");

  await page.reload();
  await expect(notesList).not.toContainText("Grocery list");
  await expect(trashTab).toHaveText("Trash (2)");

  await trashTab.click();

  const trashList = page.getByRole("list", { name: /^Trash$/ });
  await expect(trashList.getByRole("listitem")).toContainText(["Grocery list", "Old draft"]);
});

test("restores a trashed note to Notes and keeps it there after reload", async ({ page }) => {
  const trashTab = page.getByRole("tab", { name: /^Trash \(1\)$/ });
  await trashTab.click();

  const trashList = page.getByRole("list", { name: /^Trash$/ });
  const trashedNote = trashList.getByRole("listitem").filter({ hasText: "Old draft" });
  const restoreRequest = page.waitForRequest(
    (request) =>
      request.method() === "POST" &&
      new URL(request.url()).pathname === "/api/notes/4/restore",
  );

  await trashedNote.getByRole("button", { name: "Restore Old draft" }).click();
  await restoreRequest;

  await expect(trashList).not.toContainText("Old draft");
  await expect(page.getByRole("tab", { name: /^Trash \(0\)$/ })).toBeVisible();
  await expect(page.getByText("Trash is empty")).toBeVisible();

  await page.reload();

  const notesList = page.getByRole("list", { name: /^Notes$/ });
  await expect(notesList.getByRole("listitem")).toContainText([
    "Grocery list",
    "Meeting notes",
    "Gift ideas",
    "Old draft",
  ]);
  await expect(page.getByRole("tab", { name: /^Trash \(0\)$/ })).toBeVisible();
});

test("confirms and permanently empties Trash across reloads", async ({ page }) => {
  const trashTab = page.getByRole("tab", { name: /^Trash \(1\)$/ });
  await trashTab.click();
  const trashList = page.getByRole("list", { name: /^Trash$/ });
  await expect(trashList.getByRole("listitem")).toHaveCount(1);

  let confirmation = "";
  page.once("dialog", async (dialog) => {
    confirmation = dialog.message();
    await dialog.accept();
  });
  const emptyRequest = page.waitForRequest(
    (request) =>
      request.method() === "POST" &&
      new URL(request.url()).pathname === "/api/trash/empty",
  );

  await page.getByRole("button", { name: /^Empty trash$/ }).click();
  await emptyRequest;

  expect(confirmation).toBe("Permanently delete everything in the Trash?");
  await expect(page.getByText("Trash is empty")).toBeVisible();
  await expect(trashList.getByRole("listitem")).toHaveCount(0);
  await expect(page.getByRole("tab", { name: /^Trash \(0\)$/ })).toBeVisible();

  await page.reload();
  await page.getByRole("tab", { name: /^Trash \(0\)$/ }).click();
  await expect(page.getByText("Trash is empty")).toBeVisible();
  await expect(page.getByRole("list", { name: /^Trash$/ }).getByRole("listitem")).toHaveCount(0);
});
