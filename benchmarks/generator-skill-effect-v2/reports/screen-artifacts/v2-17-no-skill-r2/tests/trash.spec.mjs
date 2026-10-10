import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page, request }) => {
  const res = await request.post("/api/reset");
  expect(res.ok()).toBeTruthy();
  await page.goto("/");
  await expect(page.getByRole("tab", { name: "Trash (1)" })).toBeVisible();
});

const notesList = (page) => page.getByRole("list", { name: "Notes", exact: true });
const trashList = (page) => page.getByRole("list", { name: "Trash", exact: true });
const openTrash = (page) => page.getByRole("tab", { name: /^Trash/ }).click();
const openNotes = (page) => page.getByRole("tab", { name: "Notes" }).click();

test("shows seeded notes and trash count", async ({ page }) => {
  await expect(notesList(page).getByRole("listitem")).toHaveText([
    /Grocery list/,
    /Meeting notes/,
    /Gift ideas/,
  ]);
  await openTrash(page);
  await expect(trashList(page).getByRole("listitem")).toHaveText([/Old draft/]);
});

test("delete moves a note to the trash and updates the count", async ({ page }) => {
  await page.getByRole("button", { name: "Delete Meeting notes" }).click();
  await expect(page.getByRole("tab", { name: "Trash (2)" })).toBeVisible();
  await expect(notesList(page).getByRole("listitem")).toHaveText([/Grocery list/, /Gift ideas/]);
  await expect(page.getByText("Meeting notes")).toBeHidden();

  await openTrash(page);
  await expect(trashList(page).getByRole("listitem")).toHaveText([/Meeting notes/, /Old draft/]);
  await expect(notesList(page)).toBeHidden();
});

test("delete survives a reload", async ({ page }) => {
  await page.getByRole("button", { name: "Delete Grocery list" }).click();
  await expect(page.getByRole("tab", { name: "Trash (2)" })).toBeVisible();
  await page.reload();
  await expect(page.getByRole("tab", { name: "Trash (2)" })).toBeVisible();
  await expect(notesList(page).getByRole("listitem")).toHaveCount(2);
  await expect(notesList(page).getByText("Grocery list")).toHaveCount(0);
  await openTrash(page);
  await expect(trashList(page).getByText("Grocery list")).toBeVisible();
});

test("restore moves a note back to notes", async ({ page }) => {
  await openTrash(page);
  await page.getByRole("button", { name: "Restore Old draft" }).click();
  await expect(page.getByRole("tab", { name: "Trash (0)" })).toBeVisible();
  await expect(page.getByText("Trash is empty")).toBeVisible();
  await expect(trashList(page).getByRole("listitem")).toHaveCount(0);

  await openNotes(page);
  await expect(notesList(page).getByRole("listitem")).toHaveCount(4);
  await expect(notesList(page).getByText("Old draft")).toBeVisible();
});

test("restore survives a reload", async ({ page }) => {
  await openTrash(page);
  await page.getByRole("button", { name: "Restore Old draft" }).click();
  await expect(page.getByRole("tab", { name: "Trash (0)" })).toBeVisible();
  await page.reload();
  await expect(page.getByRole("tab", { name: "Trash (0)" })).toBeVisible();
  await expect(notesList(page).getByText("Old draft")).toBeVisible();
});

test("empty trash asks for confirmation and removes everything", async ({ page }) => {
  await page.getByRole("button", { name: "Delete Gift ideas" }).click();
  await expect(page.getByRole("tab", { name: "Trash (2)" })).toBeVisible();
  await openTrash(page);

  const messages = [];
  page.once("dialog", (dialog) => {
    messages.push(dialog.type() + ": " + dialog.message());
    return dialog.accept();
  });
  await page.getByRole("button", { name: "Empty trash" }).click();

  await expect(page.getByText("Trash is empty")).toBeVisible();
  await expect(trashList(page).getByRole("listitem")).toHaveCount(0);
  await expect(page.getByRole("tab", { name: "Trash (0)" })).toBeVisible();
  expect(messages).toEqual(["confirm: Permanently delete everything in the Trash?"]);

  await openNotes(page);
  await expect(notesList(page).getByRole("listitem")).toHaveText([/Grocery list/, /Meeting notes/]);
});

test("dismissing the empty trash confirmation keeps the trash", async ({ page }) => {
  await openTrash(page);
  page.once("dialog", (dialog) => dialog.dismiss());
  await page.getByRole("button", { name: "Empty trash" }).click();
  await expect(trashList(page).getByText("Old draft")).toBeVisible();
  await expect(page.getByRole("tab", { name: "Trash (1)" })).toBeVisible();
  await expect(page.getByText("Trash is empty")).toBeHidden();
});

test("emptied trash stays empty after a reload", async ({ page }) => {
  await openTrash(page);
  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "Empty trash" }).click();
  await expect(page.getByRole("tab", { name: "Trash (0)" })).toBeVisible();

  await page.reload();
  await expect(page.getByRole("tab", { name: "Trash (0)" })).toBeVisible();
  await openTrash(page);
  await expect(page.getByText("Trash is empty")).toBeVisible();
  await expect(page.getByRole("button", { name: "Empty trash" })).toBeDisabled();
  await openNotes(page);
  await expect(notesList(page).getByRole("listitem")).toHaveCount(3);
  await expect(notesList(page).getByText("Old draft")).toHaveCount(0);
});
