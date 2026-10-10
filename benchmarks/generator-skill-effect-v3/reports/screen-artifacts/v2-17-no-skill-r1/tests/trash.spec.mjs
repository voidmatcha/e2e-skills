import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page, request }) => {
  await request.post("/api/reset");
  await page.goto("/");
  await expect(page.getByRole("button", { name: "Delete Grocery list" })).toBeVisible();
});

const notesView = (page) => page.getByRole("list", { name: "Notes" });
const trashView = (page) => page.getByRole("list", { name: "Trash" });
const openTrash = (page) => page.getByRole("tab", { name: /^Trash/ }).click();
const openNotes = (page) => page.getByRole("tab", { name: "Notes" }).click();

test("shows seeded notes and the trashed note count", async ({ page }) => {
  await expect(notesView(page).getByRole("listitem")).toHaveText([
    /Grocery list/,
    /Meeting notes/,
    /Gift ideas/,
  ]);
  await expect(page.getByRole("tab", { name: "Trash (1)" })).toBeVisible();
  await openTrash(page);
  await expect(trashView(page).getByRole("listitem")).toHaveText([/Old draft/]);
});

test("delete moves a note from Notes to Trash", async ({ page }) => {
  await page.getByRole("button", { name: "Delete Meeting notes" }).click();
  await expect(page.getByRole("tab", { name: "Trash (2)" })).toBeVisible();
  await expect(notesView(page).getByText("Meeting notes")).toHaveCount(0);
  await expect(notesView(page).getByRole("listitem")).toHaveCount(2);

  await openTrash(page);
  await expect(trashView(page).getByRole("listitem")).toHaveCount(2);
  await expect(trashView(page).getByText("Old draft")).toBeVisible();
  await expect(trashView(page).getByText("Meeting notes")).toBeVisible();
  await openNotes(page);
  await expect(notesView(page).getByText("Meeting notes")).toHaveCount(0);
});

test("restore moves a trashed note back to Notes", async ({ page }) => {
  await openTrash(page);
  await page.getByRole("button", { name: "Restore Old draft" }).click();
  await expect(page.getByText("Trash is empty")).toBeVisible();
  await expect(page.getByRole("tab", { name: "Trash (0)" })).toBeVisible();

  await openNotes(page);
  await expect(notesView(page).getByText("Old draft")).toBeVisible();
  await expect(notesView(page).getByRole("listitem")).toHaveCount(4);
});

test("empty trash asks for confirmation and cancelling keeps the notes", async ({ page }) => {
  let message;
  page.once("dialog", (dialog) => {
    message = dialog.message();
    return dialog.dismiss();
  });
  await openTrash(page);
  await page.getByRole("button", { name: "Empty trash" }).click();
  await expect.poll(() => message).toContain("Permanently delete");
  await expect(trashView(page).getByText("Old draft")).toBeVisible();
  await expect(page.getByRole("tab", { name: "Trash (1)" })).toBeVisible();
});

test("confirming empty trash removes everything permanently", async ({ page }) => {
  await page.getByRole("button", { name: "Delete Gift ideas" }).click();
  await expect(page.getByRole("tab", { name: "Trash (2)" })).toBeVisible();
  await openTrash(page);
  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "Empty trash" }).click();

  await expect(page.getByText("Trash is empty")).toBeVisible();
  await expect(trashView(page).getByRole("listitem")).toHaveCount(0);
  await expect(page.getByRole("tab", { name: "Trash (0)" })).toBeVisible();

  await openNotes(page);
  await expect(notesView(page).getByRole("listitem")).toHaveCount(2);
  await expect(notesView(page).getByText("Gift ideas")).toHaveCount(0);
});

test("delete, restore and empty survive a reload", async ({ page }) => {
  await page.getByRole("button", { name: "Delete Grocery list" }).click();
  await expect(page.getByRole("tab", { name: "Trash (2)" })).toBeVisible();
  await page.reload();
  await expect(page.getByRole("tab", { name: "Trash (2)" })).toBeVisible();
  await expect(notesView(page).getByText("Grocery list")).toHaveCount(0);
  await openTrash(page);
  await expect(trashView(page).getByText("Grocery list")).toBeVisible();

  await page.getByRole("button", { name: "Restore Old draft" }).click();
  await expect(page.getByRole("tab", { name: "Trash (1)" })).toBeVisible();
  await page.reload();
  await expect(page.getByRole("tab", { name: "Trash (1)" })).toBeVisible();
  await expect(notesView(page).getByText("Old draft")).toBeVisible();
  await expect(notesView(page).getByText("Grocery list")).toHaveCount(0);

  await openTrash(page);
  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "Empty trash" }).click();
  await expect(page.getByText("Trash is empty")).toBeVisible();
  await page.reload();
  await expect(page.getByRole("tab", { name: "Trash (0)" })).toBeVisible();
  await openTrash(page);
  await expect(page.getByText("Trash is empty")).toBeVisible();
});
