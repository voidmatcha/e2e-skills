import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page, request }) => {
  const res = await request.post("/api/reset");
  expect(res.ok()).toBeTruthy();
  await page.goto("/");
  await expect(page.getByText("ada@example.com")).toBeVisible();
});

const openDialog = async (page) => {
  await page.getByRole("button", { name: "Delete account" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  return dialog;
};

test("confirm button is enabled only for exactly DELETE", async ({ page }) => {
  const dialog = await openDialog(page);
  const input = dialog.getByLabel("Type DELETE to confirm");
  const confirm = dialog.getByRole("button", { name: "Delete my account" });

  await expect(confirm).toBeDisabled();
  await input.fill("delete");
  await expect(confirm).toBeDisabled();
  await input.fill("DELET");
  await expect(confirm).toBeDisabled();
  await input.fill("DELETE");
  await expect(confirm).toBeEnabled();
  await input.fill("DELETE ");
  await expect(confirm).toBeDisabled();
});

for (const [name, close] of [
  ["Cancel", (page) => page.getByRole("button", { name: "Cancel" }).click()],
  ["Escape", (page) => page.keyboard.press("Escape")],
]) {
  test(`${name} closes the dialog without deleting and restores focus`, async ({ page, request }) => {
    const dialog = await openDialog(page);
    await dialog.getByLabel("Type DELETE to confirm").fill("DELETE");

    await close(page);

    await expect(dialog).toBeHidden();
    await expect(page.getByRole("button", { name: "Delete account" })).toBeFocused();
    await expect(page.getByText("ada@example.com")).toBeVisible();
    await expect(page.getByText("Your account has been deleted")).toBeHidden();
    const account = await (await request.get("/api/account")).json();
    expect(account.deleted).toBe(false);
  });
}

test("confirming deletes the account and persists after reload", async ({ page, request }) => {
  const dialog = await openDialog(page);
  await dialog.getByLabel("Type DELETE to confirm").fill("DELETE");
  await dialog.getByRole("button", { name: "Delete my account" }).click();

  await expect(page.getByText("Your account has been deleted")).toBeVisible();
  await expect(dialog).toBeHidden();
  await expect(page.getByText("ada@example.com")).toBeHidden();
  expect((await (await request.get("/api/account")).json()).deleted).toBe(true);

  await page.reload();
  await expect(page.getByText("Your account has been deleted")).toBeVisible();
  await expect(page.getByRole("button", { name: "Delete account" })).toBeHidden();
});
