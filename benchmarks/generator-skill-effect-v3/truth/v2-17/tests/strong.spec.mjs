import { expect, test } from "@playwright/test";

const notes = (page) => page.getByRole("list", { name: "Notes", exact: true }).getByRole("listitem");
const trash = (page) => page.getByRole("list", { name: "Trash", exact: true }).getByRole("listitem");
const trashTab = (page) => page.getByRole("tab", { name: /Trash/ });

test.beforeEach(async ({ page }) => {
  await page.request.post("/api/reset");
  await page.goto("/");
  await expect(notes(page)).toHaveCount(3);
  await expect(trashTab(page)).toHaveText("Trash (1)");
});

test("delete moves a note to the trash and updates the count", async ({ page }) => {
  await page.getByRole("button", { name: "Delete Meeting notes" }).click();
  await expect(notes(page)).toHaveText([/Grocery list/, /Gift ideas/]);
  await expect(trashTab(page)).toHaveText("Trash (2)");
  await trashTab(page).click();
  await expect(trash(page)).toHaveText([/Meeting notes/, /Old draft/]);
  await page.reload();
  await expect(notes(page)).toHaveText([/Grocery list/, /Gift ideas/]);
  await expect(trashTab(page)).toHaveText("Trash (2)");
});

test("restore moves a note back and out of the trash", async ({ page }) => {
  await trashTab(page).click();
  await page.getByRole("button", { name: "Restore Old draft" }).click();
  await expect(trash(page)).toHaveCount(0);
  await expect(page.getByText("Trash is empty")).toBeVisible();
  await expect(trashTab(page)).toHaveText("Trash (0)");
  await page.getByRole("tab", { name: "Notes" }).click();
  await expect(notes(page)).toHaveText([/Grocery list/, /Meeting notes/, /Gift ideas/, /Old draft/]);
  await page.reload();
  await expect(notes(page)).toHaveCount(4);
  await expect(trashTab(page)).toHaveText("Trash (0)");
});

test("empty trash asks first and is permanent", async ({ page }) => {
  await page.getByRole("button", { name: "Delete Gift ideas" }).click();
  await trashTab(page).click();
  await expect(trash(page)).toHaveCount(2);
  page.once("dialog", (dialog) => dialog.dismiss());
  await page.getByRole("button", { name: "Empty trash" }).click();
  await expect(trash(page)).toHaveCount(2);
  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "Empty trash" }).click();
  await expect(trash(page)).toHaveCount(0);
  await expect(page.getByText("Trash is empty")).toBeVisible();
  await page.reload();
  await expect(trashTab(page)).toHaveText("Trash (0)");
  await expect(notes(page)).toHaveCount(2);
  await trashTab(page).click();
  await expect(trash(page)).toHaveCount(0);
  await expect(page.getByText("Trash is empty")).toBeVisible();
});
