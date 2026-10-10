import { expect, test } from "@playwright/test";

const notesList = (page) => page.getByRole("list", { name: "Notes", exact: true });
const trashList = (page) => page.getByRole("list", { name: "Trash", exact: true });

test.beforeEach(async ({ page, request }) => {
  await request.post("/api/reset");
  await page.goto("/");
  await expect(page.getByRole("tab", { name: "Trash (1)" })).toBeVisible();
});

test("shows seeded notes and trash count", async ({ page }) => {
  await expect(notesList(page).getByRole("listitem")).toHaveText([
    /Grocery list/,
    /Meeting notes/,
    /Gift ideas/,
  ]);
  await page.getByRole("tab", { name: "Trash (1)" }).click();
  await expect(trashList(page).getByRole("listitem")).toHaveText([/Old draft/]);
});

test("delete moves a note to the trash and it survives reload", async ({ page }) => {
  await page.getByRole("button", { name: "Delete Meeting notes" }).click();
  await expect(page.getByRole("tab", { name: "Trash (2)" })).toBeVisible();
  await expect(notesList(page).getByText("Meeting notes")).toHaveCount(0);

  await page.reload();
  await expect(page.getByRole("tab", { name: "Trash (2)" })).toBeVisible();
  await expect(notesList(page).getByText("Meeting notes")).toHaveCount(0);
  await page.getByRole("tab", { name: "Trash (2)" }).click();
  await expect(trashList(page).getByRole("listitem")).toHaveText([/Meeting notes/, /Old draft/]);
  await page.getByRole("tab", { name: "Notes", exact: true }).click();
  await expect(notesList(page).getByText("Meeting notes")).toHaveCount(0);
});

test("restore moves a note back to notes and survives reload", async ({ page }) => {
  await page.getByRole("tab", { name: "Trash (1)" }).click();
  await page.getByRole("button", { name: "Restore Old draft" }).click();
  await expect(page.getByRole("tab", { name: "Trash (0)" })).toBeVisible();
  await expect(trashList(page).getByRole("listitem")).toHaveCount(0);

  await page.reload();
  await expect(page.getByRole("tab", { name: "Trash (0)" })).toBeVisible();
  await expect(notesList(page).getByRole("listitem")).toHaveCount(4);
  await expect(notesList(page).getByText("Old draft")).toBeVisible();
});

test("empty trash confirms, removes everything permanently and survives reload", async ({ page }) => {
  await page.getByRole("button", { name: "Delete Gift ideas" }).click();
  await page.getByRole("tab", { name: "Trash (2)" }).click();

  const messages = [];
  page.once("dialog", (dialog) => {
    messages.push(dialog.message());
    dialog.accept();
  });
  await page.getByRole("button", { name: "Empty trash" }).click();
  expect(messages).toEqual(["Permanently delete everything in the Trash?"]);

  await expect(page.getByText("Trash is empty")).toBeVisible();
  await expect(page.getByRole("tab", { name: "Trash (0)" })).toBeVisible();

  await page.reload();
  await page.getByRole("tab", { name: "Trash (0)" }).click();
  await expect(page.getByText("Trash is empty")).toBeVisible();
  await page.getByRole("tab", { name: "Notes", exact: true }).click();
  await expect(notesList(page).getByRole("listitem")).toHaveText([/Grocery list/, /Meeting notes/]);
});

test("dismissing the empty trash confirmation keeps the trash", async ({ page }) => {
  await page.getByRole("tab", { name: "Trash (1)" }).click();
  page.once("dialog", (dialog) => dialog.dismiss());
  await page.getByRole("button", { name: "Empty trash" }).click();

  await expect(trashList(page).getByText("Old draft")).toBeVisible();
  await page.reload();
  await expect(page.getByRole("tab", { name: "Trash (1)" })).toBeVisible();
});
