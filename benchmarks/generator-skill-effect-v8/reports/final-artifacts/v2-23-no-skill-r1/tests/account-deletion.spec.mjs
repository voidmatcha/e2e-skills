import { expect, test } from "@playwright/test";

test.beforeEach(async ({ request }) => {
  await request.post("/api/reset");
});

test("requires exactly DELETE before account deletion can be confirmed", async ({ page }) => {
  await page.goto("/");

  await page.getByRole("button", { name: "Delete account" }).click();

  const confirmText = page.getByLabel("Type DELETE to confirm");
  const confirmButton = page.getByRole("button", { name: "Delete my account" });

  await expect(confirmButton).toBeDisabled();

  await confirmText.fill("delete");
  await expect(confirmButton).toBeDisabled();

  await confirmText.fill("DELET");
  await expect(confirmButton).toBeDisabled();

  await confirmText.fill("DELETE ");
  await expect(confirmButton).toBeDisabled();

  await confirmText.fill("DELETE");
  await expect(confirmButton).toBeEnabled();
});

test("closes the deletion dialog without deleting from Escape and Cancel", async ({ page }) => {
  await page.goto("/");

  const deleteAccountButton = page.getByRole("button", { name: "Delete account" });
  const dialog = page.getByRole("dialog", { name: "Delete your account?" });

  await deleteAccountButton.click();
  await expect(dialog).toBeVisible();

  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
  await expect(deleteAccountButton).toBeFocused();
  await expect(page.getByText("Ada Lovelace")).toBeVisible();

  await deleteAccountButton.click();
  await page.getByRole("button", { name: "Cancel" }).click();
  await expect(dialog).toBeHidden();
  await expect(deleteAccountButton).toBeFocused();

  await page.reload();
  await expect(page.getByText("Ada Lovelace")).toBeVisible();
  await expect(page.getByText("Your account has been deleted")).toBeHidden();
});

test("deletes the account and keeps it deleted after reload", async ({ page }) => {
  await page.goto("/");

  await page.getByRole("button", { name: "Delete account" }).click();
  await page.getByLabel("Type DELETE to confirm").fill("DELETE");
  await page.getByRole("button", { name: "Delete my account" }).click();

  await expect(page.getByRole("status")).toHaveText("Your account has been deleted");
  await expect(page.getByText("Ada Lovelace")).toBeHidden();

  await page.reload();
  await expect(page.getByRole("status")).toHaveText("Your account has been deleted");
  await expect(page.getByText("Ada Lovelace")).toBeHidden();
});
