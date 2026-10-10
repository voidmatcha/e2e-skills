import { expect, test } from "@playwright/test";

const notesList = (page) => page.getByRole("list", { name: "Notes" });
const trashList = (page) => page.getByRole("list", { name: "Trash" });
const trashTab = (page, count) => page.getByRole("tab", { name: `Trash (${count})` });

test.beforeEach(async ({ page, request }) => {
  const res = await request.post("/api/reset");
  expect(res.ok()).toBeTruthy();
  await page.goto("/");
  await expect(notesList(page).getByRole("listitem")).toHaveCount(3);
});

test("shows seeded notes and trash count", async ({ page }) => {
  await expect(notesList(page).getByRole("listitem")).toHaveText([
    /Grocery list/,
    /Meeting notes/,
    /Gift ideas/,
  ]);
  await expect(trashTab(page, 1)).toBeVisible();
  await page.getByRole("tab", { name: /Trash/ }).click();
  await expect(trashList(page).getByRole("listitem")).toHaveText([/Old draft/]);
});

test("delete moves a note to the trash, never in both views", async ({ page }) => {
  await page.getByRole("button", { name: "Delete Meeting notes" }).click();
  await expect(notesList(page).getByText("Meeting notes")).toHaveCount(0);
  await expect(notesList(page).getByRole("listitem")).toHaveCount(2);
  await expect(trashTab(page, 2)).toBeVisible();

  await page.getByRole("tab", { name: /Trash/ }).click();
  await expect(trashList(page).getByRole("listitem")).toHaveText([/Meeting notes/, /Old draft/]);

  await page.getByRole("tab", { name: "Notes" }).click();
  await expect(notesList(page).getByText("Meeting notes")).toHaveCount(0);
});

test("restore moves a trashed note back to notes", async ({ page }) => {
  await page.getByRole("tab", { name: /Trash/ }).click();
  await page.getByRole("button", { name: "Restore Old draft" }).click();
  await expect(trashList(page).getByRole("listitem")).toHaveCount(0);
  await expect(page.getByText("Trash is empty")).toBeVisible();
  await expect(trashTab(page, 0)).toBeVisible();

  await page.getByRole("tab", { name: "Notes" }).click();
  await expect(notesList(page).getByRole("listitem")).toHaveCount(4);
  await expect(notesList(page).getByText("Old draft")).toBeVisible();
});

test("empty trash confirms and permanently removes everything", async ({ page }) => {
  await page.getByRole("button", { name: "Delete Gift ideas" }).click();
  await expect(trashTab(page, 2)).toBeVisible();
  await page.getByRole("tab", { name: /Trash/ }).click();

  const messages = [];
  page.once("dialog", (dialog) => {
    messages.push(dialog.message());
    return dialog.accept();
  });
  await page.getByRole("button", { name: "Empty trash" }).click();

  expect(messages).toHaveLength(1);
  await expect(trashList(page).getByRole("listitem")).toHaveCount(0);
  await expect(page.getByText("Trash is empty")).toBeVisible();
  await expect(trashTab(page, 0)).toBeVisible();

  await page.getByRole("tab", { name: "Notes" }).click();
  await expect(notesList(page).getByRole("listitem")).toHaveCount(2);
});

test("dismissing the empty trash confirmation keeps the trash", async ({ page }) => {
  await page.getByRole("tab", { name: /Trash/ }).click();
  page.once("dialog", (dialog) => dialog.dismiss());
  await page.getByRole("button", { name: "Empty trash" }).click();

  await expect(trashList(page).getByRole("listitem")).toHaveText([/Old draft/]);
  await expect(page.getByText("Trash is empty")).toBeHidden();
  await expect(trashTab(page, 1)).toBeVisible();
});

test("delete, restore and empty survive a reload", async ({ page }) => {
  await page.getByRole("button", { name: "Delete Grocery list" }).click();
  await expect(trashTab(page, 2)).toBeVisible();
  await page.reload();
  await expect(trashTab(page, 2)).toBeVisible();
  await expect(notesList(page).getByRole("listitem")).toHaveCount(2);
  await expect(notesList(page).getByText("Grocery list")).toHaveCount(0);

  await page.getByRole("tab", { name: /Trash/ }).click();
  await page.getByRole("button", { name: "Restore Old draft" }).click();
  await expect(trashTab(page, 1)).toBeVisible();
  await page.reload();
  await expect(trashTab(page, 1)).toBeVisible();
  await expect(notesList(page).getByText("Old draft")).toBeVisible();

  await page.getByRole("tab", { name: /Trash/ }).click();
  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "Empty trash" }).click();
  await expect(trashTab(page, 0)).toBeVisible();
  await page.reload();
  await expect(trashTab(page, 0)).toBeVisible();
  await page.getByRole("tab", { name: /Trash/ }).click();
  await expect(page.getByText("Trash is empty")).toBeVisible();
  await expect(trashList(page).getByRole("listitem")).toHaveCount(0);
});
