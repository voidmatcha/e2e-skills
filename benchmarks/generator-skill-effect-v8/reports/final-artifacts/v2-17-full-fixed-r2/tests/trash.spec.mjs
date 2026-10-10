import { expect, test } from "@playwright/test";

const noteItem = (page, listName, noteTitle) =>
  page
    .getByRole("list", { name: listName })
    .getByRole("listitem")
    .filter({ has: page.getByText(noteTitle, { exact: true }) });

const trashTab = (page) => page.getByRole("tab", { name: /^Trash \(\d+\)$/ });

test.beforeEach(async ({ page }) => {
  await page.request.post("/api/reset");
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Notes" })).toBeVisible();
});

test("shows seeded notes separately from the trash view", async ({ page }) => {
  await expect(trashTab(page)).toHaveText("Trash (1)");
  await expect(page.getByRole("list", { name: "Notes" }).getByRole("listitem")).toHaveCount(3);
  await expect(noteItem(page, "Notes", "Grocery list")).toBeVisible();
  await expect(noteItem(page, "Notes", "Meeting notes")).toBeVisible();
  await expect(noteItem(page, "Notes", "Gift ideas")).toBeVisible();
  await expect(noteItem(page, "Notes", "Old draft")).toHaveCount(0);

  await trashTab(page).click();

  await expect(noteItem(page, "Trash", "Old draft")).toBeVisible();
  await expect(noteItem(page, "Trash", "Grocery list")).toHaveCount(0);
});

test("moves a deleted note to trash and keeps it there after reload", async ({ page }) => {
  const trashRequest = page.waitForRequest(
    (request) => request.method() === "POST" && request.url().endsWith("/api/notes/1/trash"),
  );

  await page.getByRole("button", { name: "Delete Grocery list" }).click();
  const request = await trashRequest;

  expect(request.method()).toBe("POST");
  await expect(trashTab(page)).toHaveText("Trash (2)");
  await expect(noteItem(page, "Notes", "Grocery list")).toHaveCount(0);

  await trashTab(page).click();
  await expect(noteItem(page, "Trash", "Grocery list")).toBeVisible();

  await page.reload();
  await expect(trashTab(page)).toHaveText("Trash (2)");
  await expect(noteItem(page, "Notes", "Grocery list")).toHaveCount(0);

  await trashTab(page).click();
  await expect(noteItem(page, "Trash", "Grocery list")).toBeVisible();
});

test("restores a trashed note to notes and keeps it there after reload", async ({ page }) => {
  await trashTab(page).click();
  const restoreRequest = page.waitForRequest(
    (request) => request.method() === "POST" && request.url().endsWith("/api/notes/4/restore"),
  );

  await page.getByRole("button", { name: "Restore Old draft" }).click();
  const request = await restoreRequest;

  expect(request.method()).toBe("POST");
  await expect(trashTab(page)).toHaveText("Trash (0)");
  await expect(noteItem(page, "Trash", "Old draft")).toHaveCount(0);

  await page.getByRole("tab", { name: "Notes" }).click();
  await expect(noteItem(page, "Notes", "Old draft")).toBeVisible();

  await page.reload();
  await expect(trashTab(page)).toHaveText("Trash (0)");
  await expect(noteItem(page, "Notes", "Old draft")).toBeVisible();
});

test("confirms empty trash and permanently removes all trashed notes after reload", async ({ page }) => {
  const trashRequest = page.waitForRequest(
    (request) => request.method() === "POST" && request.url().endsWith("/api/notes/3/trash"),
  );
  await page.getByRole("button", { name: "Delete Gift ideas" }).click();
  await trashRequest;
  await expect(trashTab(page)).toHaveText("Trash (2)");

  await trashTab(page).click();
  await expect(noteItem(page, "Trash", "Old draft")).toBeVisible();
  await expect(noteItem(page, "Trash", "Gift ideas")).toBeVisible();

  let dialogMessage = "";
  const dialogPromise = new Promise((resolve) => {
    page.once("dialog", async (dialog) => {
      dialogMessage = dialog.message();
      await dialog.accept();
      resolve();
    });
  });
  const emptyRequest = page.waitForRequest(
    (request) => request.method() === "POST" && request.url().endsWith("/api/trash/empty"),
  );

  await page.getByRole("button", { name: "Empty trash" }).click();
  await dialogPromise;
  expect(dialogMessage).toBe("Permanently delete everything in the Trash?");
  const request = await emptyRequest;

  expect(request.method()).toBe("POST");
  await expect(trashTab(page)).toHaveText("Trash (0)");
  await expect(page.getByText("Trash is empty")).toBeVisible();
  await expect(page.getByRole("button", { name: "Empty trash" })).toBeDisabled();
  await expect(page.getByRole("list", { name: "Trash" }).getByRole("listitem")).toHaveCount(0);

  await page.reload();
  await expect(trashTab(page)).toHaveText("Trash (0)");
  await expect(noteItem(page, "Notes", "Old draft")).toHaveCount(0);
  await expect(noteItem(page, "Notes", "Gift ideas")).toHaveCount(0);

  await trashTab(page).click();
  await expect(page.getByText("Trash is empty")).toBeVisible();
});
