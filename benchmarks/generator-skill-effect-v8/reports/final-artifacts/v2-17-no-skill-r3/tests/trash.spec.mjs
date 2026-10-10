import { expect, test } from "@playwright/test";

test.beforeEach(async ({ request }) => {
  await request.post("/api/reset");
});

test("moves deleted notes to trash and keeps them there after reload", async ({ page }) => {
  await page.goto("/");

  const notes = page.getByRole("list", { name: "Notes" });
  const trash = page.getByRole("list", { name: "Trash" });
  const trashTab = page.getByRole("tab", { name: /^Trash/ });

  await expect(notes.getByText("Grocery list")).toBeVisible();
  await expect(notes.getByText("Meeting notes")).toBeVisible();
  await expect(notes.getByText("Gift ideas")).toBeVisible();
  await expect(notes.getByText("Old draft")).toHaveCount(0);
  await expect(trashTab).toHaveText("Trash (1)");

  await page.getByRole("button", { name: "Delete Grocery list" }).click();
  await expect(notes.getByText("Grocery list")).toHaveCount(0);
  await expect(trashTab).toHaveText("Trash (2)");

  await trashTab.click();
  await expect(trash.getByText("Grocery list")).toBeVisible();
  await expect(trash.getByText("Old draft")).toBeVisible();
  await expect(notes.getByText("Grocery list")).toHaveCount(0);

  await page.reload();
  await trashTab.click();
  await expect(trash.getByText("Grocery list")).toBeVisible();
  await expect(trash.getByText("Old draft")).toBeVisible();
  await expect(trashTab).toHaveText("Trash (2)");
});

test("restores a trashed note to notes and persists after reload", async ({ page }) => {
  await page.goto("/");

  const notes = page.getByRole("list", { name: "Notes" });
  const trash = page.getByRole("list", { name: "Trash" });

  await page.getByRole("tab", { name: "Trash (1)" }).click();
  await page.getByRole("button", { name: "Restore Old draft" }).click();

  await expect(trash.getByText("Old draft")).toHaveCount(0);
  await expect(page.getByRole("tab", { name: "Trash (0)" })).toBeVisible();

  await page.getByRole("tab", { name: "Notes" }).click();
  await expect(notes.getByText("Old draft")).toBeVisible();

  await page.reload();
  await expect(notes.getByText("Old draft")).toBeVisible();
  await expect(page.getByRole("tab", { name: "Trash (0)" })).toBeVisible();
});

test("empties trash after confirmation and persists after reload", async ({ page }) => {
  await page.goto("/");

  const trash = page.getByRole("list", { name: "Trash" });
  const trashTab = page.getByRole("tab", { name: /^Trash/ });

  await page.getByRole("button", { name: "Delete Meeting notes" }).click();
  await expect(trashTab).toHaveText("Trash (2)");

  await trashTab.click();
  await expect(trash.getByText("Old draft")).toBeVisible();
  await expect(trash.getByText("Meeting notes")).toBeVisible();

  page.once("dialog", async (dialog) => {
    expect(dialog.message()).toBe("Permanently delete everything in the Trash?");
    await dialog.accept();
  });
  await page.getByRole("button", { name: "Empty trash" }).click();

  await expect(page.getByText("Trash is empty")).toBeVisible();
  await expect(page.getByRole("button", { name: "Empty trash" })).toBeDisabled();
  await expect(trashTab).toHaveText("Trash (0)");
  await expect(trash.getByText("Old draft")).toHaveCount(0);
  await expect(trash.getByText("Meeting notes")).toHaveCount(0);

  await page.reload();
  await trashTab.click();
  await expect(page.getByText("Trash is empty")).toBeVisible();
  await expect(trashTab).toHaveText("Trash (0)");
  await expect(trash.getByText("Old draft")).toHaveCount(0);
  await expect(trash.getByText("Meeting notes")).toHaveCount(0);
});
