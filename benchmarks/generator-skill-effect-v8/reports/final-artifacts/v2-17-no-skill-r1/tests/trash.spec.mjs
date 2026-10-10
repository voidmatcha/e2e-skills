import { expect, test } from "@playwright/test";

test.beforeEach(async ({ request }) => {
  await request.post("/api/reset");
});

test("shows seeded notes separately from the Trash view", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByRole("heading", { name: "Notes" })).toBeVisible();
  await expect(page.getByRole("tab", { name: "Trash (1)" })).toBeVisible();

  const notes = page.getByRole("list", { name: "Notes" });
  await expect(notes.getByText("Grocery list")).toBeVisible();
  await expect(notes.getByText("Meeting notes")).toBeVisible();
  await expect(notes.getByText("Gift ideas")).toBeVisible();
  await expect(notes.getByText("Old draft")).toHaveCount(0);

  await page.getByRole("tab", { name: "Trash (1)" }).click();

  const trash = page.getByRole("list", { name: "Trash" });
  await expect(trash.getByText("Old draft")).toBeVisible();
  await expect(trash.getByText("Grocery list")).toHaveCount(0);
  await expect(trash.getByText("Meeting notes")).toHaveCount(0);
  await expect(trash.getByText("Gift ideas")).toHaveCount(0);
});

test("moves a deleted note to Trash and keeps it there after reload", async ({ page }) => {
  await page.goto("/");

  await page.getByRole("button", { name: "Delete Grocery list" }).click();
  await expect(page.getByRole("tab", { name: "Trash (2)" })).toBeVisible();

  const notes = page.getByRole("list", { name: "Notes" });
  await expect(notes.getByText("Grocery list")).toHaveCount(0);
  await expect(notes.getByText("Meeting notes")).toBeVisible();
  await expect(notes.getByText("Gift ideas")).toBeVisible();

  await page.reload();

  await expect(page.getByRole("tab", { name: "Trash (2)" })).toBeVisible();
  await expect(notes.getByText("Grocery list")).toHaveCount(0);

  await page.getByRole("tab", { name: "Trash (2)" }).click();

  const trash = page.getByRole("list", { name: "Trash" });
  await expect(trash.getByText("Grocery list")).toBeVisible();
  await expect(trash.getByText("Old draft")).toBeVisible();
  await expect(trash.getByText("Meeting notes")).toHaveCount(0);
});

test("restores a trashed note to Notes and persists after reload", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("tab", { name: "Trash (1)" }).click();

  await page.getByRole("button", { name: "Restore Old draft" }).click();
  await expect(page.getByRole("tab", { name: "Trash (0)" })).toBeVisible();
  await expect(page.getByText("Trash is empty")).toBeVisible();

  await page.getByRole("tab", { name: "Notes" }).click();
  await expect(page.getByRole("list", { name: "Notes" }).getByText("Old draft")).toBeVisible();

  await page.reload();

  await expect(page.getByRole("tab", { name: "Trash (0)" })).toBeVisible();
  await expect(page.getByRole("list", { name: "Notes" }).getByText("Old draft")).toBeVisible();
  await page.getByRole("tab", { name: "Trash (0)" }).click();
  await expect(page.getByText("Trash is empty")).toBeVisible();
});

test("confirms and permanently empties Trash across reloads", async ({ page }) => {
  await page.goto("/");

  await page.getByRole("button", { name: "Delete Grocery list" }).click();
  await page.getByRole("tab", { name: "Trash (2)" }).click();

  page.once("dialog", async (dialog) => {
    expect(dialog.message()).toBe("Permanently delete everything in the Trash?");
    await dialog.accept();
  });
  await page.getByRole("button", { name: "Empty trash" }).click();

  await expect(page.getByRole("tab", { name: "Trash (0)" })).toBeVisible();
  await expect(page.getByText("Trash is empty")).toBeVisible();
  await expect(page.getByRole("button", { name: "Empty trash" })).toBeDisabled();
  await expect(page.getByRole("list", { name: "Trash" }).getByRole("listitem")).toHaveCount(0);

  await page.reload();
  await expect(page.getByRole("tab", { name: "Trash (0)" })).toBeVisible();
  await page.getByRole("tab", { name: "Trash (0)" }).click();
  await expect(page.getByText("Trash is empty")).toBeVisible();

  await page.getByRole("tab", { name: "Notes" }).click();
  const notes = page.getByRole("list", { name: "Notes" });
  await expect(notes.getByText("Grocery list")).toHaveCount(0);
  await expect(notes.getByText("Old draft")).toHaveCount(0);
  await expect(notes.getByText("Meeting notes")).toBeVisible();
  await expect(notes.getByText("Gift ideas")).toBeVisible();
});
