import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page, request }) => {
  await request.post("/api/reset");
  await page.goto("/");
  await expect(page.getByText(/^Ada Lovelace$/)).toBeVisible();
});

test("keeps account deletion disabled until DELETE is typed exactly", async ({ page }) => {
  await page.getByRole("button", { name: /^Delete account$/ }).click();

  const confirmText = page.getByLabel("Type DELETE to confirm");
  const deleteAccount = page.getByRole("button", { name: /^Delete my account$/ });

  await expect(page.getByRole("dialog", { name: /^Delete your account\?$/ })).toBeVisible();
  await expect(deleteAccount).toBeDisabled();

  await confirmText.fill("delete");
  await expect(deleteAccount).toBeDisabled();

  await confirmText.fill("DELET");
  await expect(deleteAccount).toBeDisabled();

  await confirmText.fill("DELETE");
  await expect(deleteAccount).toBeEnabled();
});

test("closes the deletion dialog with Escape without deleting the account", async ({ page }) => {
  const openDeletion = page.getByRole("button", { name: /^Delete account$/ });

  await openDeletion.click();
  await expect(page.getByRole("dialog", { name: /^Delete your account\?$/ })).toBeVisible();

  await page.keyboard.press("Escape");

  await expect(page.getByRole("dialog", { name: /^Delete your account\?$/ })).toBeHidden();
  await expect(openDeletion).toBeFocused();

  await page.reload();
  await expect(page.getByText(/^Ada Lovelace$/)).toBeVisible();
});

test("closes the deletion dialog with Cancel without deleting the account", async ({ page }) => {
  const openDeletion = page.getByRole("button", { name: /^Delete account$/ });

  await openDeletion.click();
  await expect(page.getByRole("dialog", { name: /^Delete your account\?$/ })).toBeVisible();

  await page.getByRole("button", { name: /^Cancel$/ }).click();

  await expect(page.getByRole("dialog", { name: /^Delete your account\?$/ })).toBeHidden();
  await expect(openDeletion).toBeFocused();

  await page.reload();
  await expect(page.getByText(/^Ada Lovelace$/)).toBeVisible();
});

test("deletes the account and keeps it deleted after reload", async ({ page }) => {
  await page.getByRole("button", { name: /^Delete account$/ }).click();
  await page.getByLabel("Type DELETE to confirm").fill("DELETE");

  const deleteRequest = page.waitForRequest(
    (request) => request.method() === "DELETE" && new URL(request.url()).pathname === "/api/account",
  );
  await page.getByRole("button", { name: /^Delete my account$/ }).click();
  await deleteRequest;

  await expect(page.getByRole("status")).toHaveText("Your account has been deleted");

  await page.reload();
  await expect(page.getByRole("status")).toHaveText("Your account has been deleted");
});
