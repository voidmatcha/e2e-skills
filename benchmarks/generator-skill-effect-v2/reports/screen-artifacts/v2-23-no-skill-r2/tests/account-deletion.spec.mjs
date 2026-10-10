import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page, request }) => {
  const res = await request.post("/api/reset");
  expect(res.ok()).toBeTruthy();
  await page.goto("/");
  await expect(page.locator("#ac-name")).toHaveText("Ada Lovelace");
});

const openDialog = async (page) => {
  await page.getByRole("button", { name: "Delete account" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  return dialog;
};

test("confirm button is enabled only for exactly DELETE", async ({ page }) => {
  const dialog = await openDialog(page);
  const confirm = dialog.getByRole("button", { name: "Delete my account" });
  const input = dialog.getByLabel("Type DELETE to confirm");
  await expect(confirm).toBeDisabled();
  for (const text of ["delete", "DELET", "Delete", "DELETE "]) {
    await input.fill(text);
    await expect(confirm).toBeDisabled();
  }
  await input.fill("DELETE");
  await expect(confirm).toBeEnabled();
});

test("Cancel closes the dialog without deleting and restores focus", async ({ page, request }) => {
  const dialog = await openDialog(page);
  await dialog.getByLabel("Type DELETE to confirm").fill("DELETE");
  await dialog.getByRole("button", { name: "Cancel" }).click();
  await expect(dialog).toBeHidden();
  await expect(page.getByRole("button", { name: "Delete account" })).toBeFocused();
  await expect(page.locator("#ac-name")).toHaveText("Ada Lovelace");
  expect((await (await request.get("/api/account")).json()).deleted).toBe(false);
});

test("Escape closes the dialog without deleting and restores focus", async ({ page, request }) => {
  const dialog = await openDialog(page);
  await dialog.getByLabel("Type DELETE to confirm").fill("DELETE");
  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
  await expect(page.getByRole("button", { name: "Delete account" })).toBeFocused();
  await expect(page.locator("#ac-name")).toHaveText("Ada Lovelace");
  expect((await (await request.get("/api/account")).json()).deleted).toBe(false);
});

test("confirming deletes the account and persists after reload", async ({ page, request }) => {
  const dialog = await openDialog(page);
  await dialog.getByLabel("Type DELETE to confirm").fill("DELETE");
  await dialog.getByRole("button", { name: "Delete my account" }).click();
  await expect(page.getByText("Your account has been deleted")).toBeVisible();
  await expect(dialog).toBeHidden();
  await expect(page.getByRole("button", { name: "Delete account" })).toBeHidden();
  expect((await (await request.get("/api/account")).json()).deleted).toBe(true);

  await page.reload();
  await expect(page.getByText("Your account has been deleted")).toBeVisible();
  await expect(page.getByRole("button", { name: "Delete account" })).toBeHidden();
});
