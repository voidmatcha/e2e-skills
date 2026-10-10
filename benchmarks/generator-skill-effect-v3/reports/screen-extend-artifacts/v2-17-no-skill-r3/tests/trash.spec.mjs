import { expect, test } from "@playwright/test";

const notesList = (page) => page.getByRole("list", { name: "Notes" });
const trashList = (page) => page.getByRole("list", { name: "Trash" });

test.beforeEach(async ({ page, request }) => {
  const res = await request.post("/api/reset");
  expect(res.ok()).toBeTruthy();
  await page.goto("/");
  await expect(notesList(page).getByRole("listitem")).toHaveCount(3);
});

test("shows seeded notes and the trashed note count", async ({ page }) => {
  await expect(notesList(page)).toContainText("Grocery list");
  await expect(notesList(page)).toContainText("Meeting notes");
  await expect(notesList(page)).toContainText("Gift ideas");
  await expect(notesList(page)).not.toContainText("Old draft");
  await expect(page.getByRole("tab", { name: "Trash (1)" })).toBeVisible();
  await page.getByRole("tab", { name: /Trash/ }).click();
  await expect(trashList(page).getByRole("listitem")).toHaveText(/Old draft/);
});

test("delete moves a note to the Trash and updates the count", async ({ page }) => {
  await page.getByRole("button", { name: "Delete Meeting notes" }).click();

  await expect(notesList(page).getByRole("listitem")).toHaveCount(2);
  await expect(notesList(page)).not.toContainText("Meeting notes");
  await expect(page.getByRole("tab", { name: "Trash (2)" })).toBeVisible();

  await page.getByRole("tab", { name: "Trash (2)" }).click();
  await expect(trashList(page).getByRole("listitem")).toHaveCount(2);
  await expect(trashList(page)).toContainText("Meeting notes");
  await expect(trashList(page)).toContainText("Old draft");
});

test("restore moves a trashed note back to Notes", async ({ page }) => {
  await page.getByRole("tab", { name: "Trash (1)" }).click();
  await page.getByRole("button", { name: "Restore Old draft" }).click();

  await expect(page.getByText("Trash is empty")).toBeVisible();
  await expect(page.getByRole("tab", { name: "Trash (0)" })).toBeVisible();

  await page.getByRole("tab", { name: "Notes" }).click();
  await expect(notesList(page).getByRole("listitem")).toHaveCount(4);
  await expect(notesList(page)).toContainText("Old draft");
});

test("empty trash confirms, then permanently removes everything", async ({ page }) => {
  await page.getByRole("button", { name: "Delete Gift ideas" }).click();
  await page.getByRole("tab", { name: "Trash (2)" }).click();

  const dialogs = [];
  page.once("dialog", (dialog) => {
    dialogs.push(dialog.message());
    return dialog.accept();
  });
  await page.getByRole("button", { name: "Empty trash" }).click();

  await expect(page.getByText("Trash is empty")).toBeVisible();
  await expect(trashList(page).getByRole("listitem")).toHaveCount(0);
  await expect(page.getByRole("tab", { name: "Trash (0)" })).toBeVisible();
  expect(dialogs).toHaveLength(1);

  await page.getByRole("tab", { name: "Notes" }).click();
  await expect(notesList(page).getByRole("listitem")).toHaveCount(2);
});

test("dismissing the empty trash confirmation keeps the Trash", async ({ page }) => {
  await page.getByRole("tab", { name: "Trash (1)" }).click();
  page.once("dialog", (dialog) => dialog.dismiss());
  await page.getByRole("button", { name: "Empty trash" }).click();

  await expect(trashList(page)).toContainText("Old draft");
  await expect(page.getByRole("tab", { name: "Trash (1)" })).toBeVisible();
  await page.reload();
  await expect(page.getByRole("tab", { name: "Trash (1)" })).toBeVisible();
});

test("delete and restore survive a reload and never show a note in both views", async ({ page }) => {
  await page.getByRole("button", { name: "Delete Grocery list" }).click();
  await expect(page.getByRole("tab", { name: "Trash (2)" })).toBeVisible();

  await page.reload();
  await expect(page.getByRole("tab", { name: "Trash (2)" })).toBeVisible();
  await expect(notesList(page)).not.toContainText("Grocery list");
  await page.getByRole("tab", { name: "Trash (2)" }).click();
  await expect(trashList(page)).toContainText("Grocery list");

  await page.getByRole("button", { name: "Restore Grocery list" }).click();
  await page.reload();
  await expect(page.getByRole("tab", { name: "Trash (1)" })).toBeVisible();
  await expect(notesList(page)).toContainText("Grocery list");
  await page.getByRole("tab", { name: "Trash (1)" }).click();
  await expect(trashList(page)).not.toContainText("Grocery list");
});

test("emptying the trash survives a reload", async ({ page }) => {
  await page.getByRole("tab", { name: "Trash (1)" }).click();
  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "Empty trash" }).click();
  await expect(page.getByText("Trash is empty")).toBeVisible();

  await page.reload();
  await expect(page.getByRole("tab", { name: "Trash (0)" })).toBeVisible();
  await page.getByRole("tab", { name: "Trash (0)" }).click();
  await expect(page.getByText("Trash is empty")).toBeVisible();
  await page.getByRole("tab", { name: "Notes" }).click();
  await expect(notesList(page).getByRole("listitem")).toHaveCount(3);
  await expect(notesList(page)).not.toContainText("Old draft");
});
