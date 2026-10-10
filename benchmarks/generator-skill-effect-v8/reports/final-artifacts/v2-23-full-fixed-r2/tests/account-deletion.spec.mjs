import { expect, test } from "@playwright/test";

test.beforeEach(async ({ request }) => {
  await request.post("/api/reset");
});

test("requires exactly DELETE before enabling account deletion", async ({ page }) => {
  await page.goto("/");

  await page.getByRole("button", { name: "Delete account", exact: true }).click();

  const confirmInput = page.getByRole("textbox", { name: "Type DELETE to confirm", exact: true });
  const confirmButton = page.getByRole("button", { name: "Delete my account", exact: true });

  await expect(confirmButton).toBeDisabled();

  await confirmInput.fill("delete");
  await expect(confirmButton).toBeDisabled();

  await confirmInput.fill("DEL");
  await expect(confirmButton).toBeDisabled();

  await confirmInput.fill("DELETE");
  await expect(confirmButton).toBeEnabled();
});

test("closes the delete dialog without deleting from cancel and escape", async ({ page }) => {
  await page.goto("/");

  const openButton = page.getByRole("button", { name: "Delete account", exact: true });
  const dialog = page.getByRole("dialog", { name: "Delete your account?", exact: true });
  const profileName = page.getByText("Ada Lovelace");

  await openButton.click();
  await expect(dialog).toBeVisible();

  await page.getByRole("button", { name: "Cancel", exact: true }).click();
  await expect(dialog).toBeHidden();
  await expect(openButton).toBeFocused();
  await expect(profileName).toBeVisible();

  await openButton.click();
  await expect(dialog).toBeVisible();

  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
  await expect(openButton).toBeFocused();
  await expect(profileName).toBeVisible();
});

test("deletes the account and persists the deleted state after reload", async ({ page }) => {
  await page.goto("/");

  const profileName = page.getByText("Ada Lovelace");

  await expect(profileName).toBeVisible();

  await page.getByRole("button", { name: "Delete account", exact: true }).click();
  await page.getByRole("textbox", { name: "Type DELETE to confirm", exact: true }).fill("DELETE");

  const deletionRequest = page.waitForRequest((request) => {
    const url = new URL(request.url());
    return request.method() === "DELETE" && url.pathname === "/api/account";
  });

  await page.getByRole("button", { name: "Delete my account", exact: true }).click();
  await deletionRequest;

  await expect(page.getByRole("status")).toHaveText("Your account has been deleted");
  await expect(profileName).toBeHidden();

  await page.reload();
  await expect(page.getByRole("status")).toHaveText("Your account has been deleted");
  await expect(profileName).toBeHidden();
});
