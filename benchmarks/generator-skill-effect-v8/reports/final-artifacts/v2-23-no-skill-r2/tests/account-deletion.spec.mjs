import { expect, test } from "@playwright/test";

test.beforeEach(async ({ request }) => {
  await request.post("/api/reset");
});

test("requires exactly DELETE before enabling account deletion", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Delete account" }).click();

  const dialog = page.getByRole("dialog", { name: "Delete your account?" });
  const confirmation = dialog.getByLabel("Type DELETE to confirm");
  const deleteButton = dialog.getByRole("button", { name: "Delete my account" });

  await expect(deleteButton).toBeDisabled();

  await confirmation.fill("delete");
  await expect(deleteButton).toBeDisabled();

  await confirmation.fill("DELET");
  await expect(deleteButton).toBeDisabled();

  await confirmation.fill("DELETE ");
  await expect(deleteButton).toBeDisabled();

  await confirmation.fill("DELETE");
  await expect(deleteButton).toBeEnabled();
});

test("closes the deletion dialog with Cancel without deleting the account", async ({ page }) => {
  await page.goto("/");
  const openButton = page.getByRole("button", { name: "Delete account" });
  await openButton.click();

  const dialog = page.getByRole("dialog", { name: "Delete your account?" });
  await dialog.getByRole("button", { name: "Cancel" }).click();

  await expect(dialog).toBeHidden();
  await expect(openButton).toBeFocused();
  await expect(page.getByText("Ada Lovelace")).toBeVisible();
  await expect(page.getByText("Your account has been deleted")).toBeHidden();
});

test("closes the deletion dialog with Escape without deleting the account", async ({ page }) => {
  await page.goto("/");
  const openButton = page.getByRole("button", { name: "Delete account" });
  await openButton.click();

  const dialog = page.getByRole("dialog", { name: "Delete your account?" });
  await page.keyboard.press("Escape");

  await expect(dialog).toBeHidden();
  await expect(openButton).toBeFocused();
  await expect(page.getByText("Ada Lovelace")).toBeVisible();
  await expect(page.getByText("Your account has been deleted")).toBeHidden();
});

test("deletes the account and persists the deleted state after reload", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Delete account" }).click();

  const dialog = page.getByRole("dialog", { name: "Delete your account?" });
  await dialog.getByLabel("Type DELETE to confirm").fill("DELETE");
  await dialog.getByRole("button", { name: "Delete my account" }).click();

  await expect(page.getByText("Your account has been deleted")).toBeVisible();
  await expect(page.getByText("Ada Lovelace")).toBeHidden();

  await page.reload();

  await expect(page.getByText("Your account has been deleted")).toBeVisible();
  await expect(page.getByText("Ada Lovelace")).toBeHidden();
});
