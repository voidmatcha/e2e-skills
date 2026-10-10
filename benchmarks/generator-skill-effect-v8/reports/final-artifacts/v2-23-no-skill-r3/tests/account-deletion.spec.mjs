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

  await confirmText.fill("DELETE");
  await expect(confirmButton).toBeEnabled();
});

test("cancel closes the deletion dialog without deleting the account", async ({ page }) => {
  await page.goto("/");

  const deleteAccountButton = page.getByRole("button", { name: "Delete account" });
  await deleteAccountButton.click();

  await page.getByRole("button", { name: "Cancel" }).click();

  await expect(page.getByRole("dialog", { name: "Delete your account?" })).toBeHidden();
  await expect(deleteAccountButton).toBeFocused();
  await expect(page.getByText("Ada Lovelace")).toBeVisible();
  await expect(page.getByText("Your account has been deleted")).toBeHidden();
});

test("escape closes the deletion dialog without deleting the account", async ({ page }) => {
  await page.goto("/");

  const deleteAccountButton = page.getByRole("button", { name: "Delete account" });
  await deleteAccountButton.click();

  await page.keyboard.press("Escape");

  await expect(page.getByRole("dialog", { name: "Delete your account?" })).toBeHidden();
  await expect(deleteAccountButton).toBeFocused();
  await expect(page.getByText("Ada Lovelace")).toBeVisible();
  await expect(page.getByText("Your account has been deleted")).toBeHidden();
});

test("confirmed account deletion persists after reload", async ({ page }) => {
  await page.goto("/");

  await page.getByRole("button", { name: "Delete account" }).click();
  await page.getByLabel("Type DELETE to confirm").fill("DELETE");
  await page.getByRole("button", { name: "Delete my account" }).click();

  await expect(page.getByText("Your account has been deleted")).toBeVisible();
  await expect(page.getByText("Ada Lovelace")).toBeHidden();

  await page.reload();

  await expect(page.getByText("Your account has been deleted")).toBeVisible();
  await expect(page.getByText("Ada Lovelace")).toBeHidden();
});
