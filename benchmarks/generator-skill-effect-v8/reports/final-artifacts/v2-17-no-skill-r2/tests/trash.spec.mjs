import { expect, test } from "@playwright/test";

const resetNotes = async ({ request }) => {
  await request.post("/api/reset");
};

const notesList = (page) => page.getByRole("list", { name: "Notes" });
const trashList = (page) => page.getByRole("list", { name: "Trash" });
const trashTab = (page, count) => page.getByRole("tab", { name: `Trash (${count})` });

test.beforeEach(resetNotes);

test("shows seeded notes and trash in separate views", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByRole("tab", { name: "Notes", selected: true })).toBeVisible();
  await expect(trashTab(page, 1)).toBeVisible();
  await expect(notesList(page)).toContainText("Grocery list");
  await expect(notesList(page)).toContainText("Meeting notes");
  await expect(notesList(page)).toContainText("Gift ideas");
  await expect(notesList(page)).not.toContainText("Old draft");

  await trashTab(page, 1).click();

  await expect(page.getByRole("tab", { name: "Trash (1)", selected: true })).toBeVisible();
  await expect(trashList(page)).toContainText("Old draft");
  await expect(trashList(page)).not.toContainText("Grocery list");
  await expect(trashList(page)).not.toContainText("Meeting notes");
  await expect(trashList(page)).not.toContainText("Gift ideas");
});

test("moves a deleted note to trash and keeps it there after reload", async ({ page }) => {
  await page.goto("/");

  await page.getByRole("button", { name: "Delete Meeting notes" }).click();

  await expect(trashTab(page, 2)).toBeVisible();
  await expect(notesList(page)).not.toContainText("Meeting notes");

  await trashTab(page, 2).click();
  await expect(trashList(page)).toContainText("Meeting notes");
  await expect(trashList(page)).toContainText("Old draft");

  await page.reload();

  await expect(trashTab(page, 2)).toBeVisible();
  await expect(notesList(page)).not.toContainText("Meeting notes");

  await trashTab(page, 2).click();
  await expect(trashList(page)).toContainText("Meeting notes");
  await expect(trashList(page)).toContainText("Old draft");
});

test("restores a trashed note to notes and keeps it there after reload", async ({ page }) => {
  await page.goto("/");
  await trashTab(page, 1).click();

  await page.getByRole("button", { name: "Restore Old draft" }).click();

  await expect(trashTab(page, 0)).toBeVisible();
  await expect(trashList(page)).not.toContainText("Old draft");
  await expect(page.getByText("Trash is empty")).toBeVisible();

  await page.getByRole("tab", { name: "Notes" }).click();
  await expect(notesList(page)).toContainText("Old draft");

  await page.reload();

  await expect(trashTab(page, 0)).toBeVisible();
  await expect(notesList(page)).toContainText("Old draft");

  await trashTab(page, 0).click();
  await expect(page.getByText("Trash is empty")).toBeVisible();
  await expect(trashList(page)).not.toContainText("Old draft");
});

test("confirms empty trash, permanently removes trashed notes, and persists after reload", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Delete Gift ideas" }).click();
  await trashTab(page, 2).click();

  page.once("dialog", async (dialog) => {
    expect(dialog.message()).toBe("Permanently delete everything in the Trash?");
    await dialog.accept();
  });
  await page.getByRole("button", { name: "Empty trash" }).click();

  await expect(trashTab(page, 0)).toBeVisible();
  await expect(page.getByText("Trash is empty")).toBeVisible();
  await expect(trashList(page)).not.toContainText("Gift ideas");
  await expect(trashList(page)).not.toContainText("Old draft");

  await page.getByRole("tab", { name: "Notes" }).click();
  await expect(notesList(page)).not.toContainText("Gift ideas");
  await expect(notesList(page)).not.toContainText("Old draft");

  await page.reload();
  await expect(trashTab(page, 0)).toBeVisible();
  await expect(notesList(page)).not.toContainText("Gift ideas");
  await expect(notesList(page)).not.toContainText("Old draft");

  await trashTab(page, 0).click();
  await expect(page.getByText("Trash is empty")).toBeVisible();
});
