import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page, request }) => {
  await request.post("/api/reset");
  await page.goto("/");
  await expect(page.getByText("Ada Lovelace")).toBeVisible();
});

test("requires exactly DELETE before enabling account deletion", async ({ page }) => {
  const deleteAccountButton = page.getByRole("button", { name: "Delete account", exact: true });
  const confirmInput = page.getByLabel("Type DELETE to confirm");
  const confirmButton = page.getByRole("button", { name: "Delete my account", exact: true });

  await deleteAccountButton.click();
  await expect(page.getByRole("dialog", { name: "Delete your account?", exact: true })).toBeVisible();
  await expect(confirmButton).toBeDisabled();

  await confirmInput.fill("DEL");
  await expect(confirmButton).toBeDisabled();

  await confirmInput.fill("delete");
  await expect(confirmButton).toBeDisabled();

  await confirmInput.fill("DELETE");
  await expect(confirmButton).toBeEnabled();
});

test("closes the confirmation dialog without deleting via Escape or Cancel", async ({ page }) => {
  const deleteAccountButton = page.getByRole("button", { name: "Delete account", exact: true });
  const dialog = page.getByRole("dialog", { name: "Delete your account?", exact: true, includeHidden: true });
  const cancelButton = page.getByRole("button", { name: "Cancel", exact: true });

  await deleteAccountButton.click();
  await expect(dialog).toBeVisible();
  await page.keyboard.press("Escape");

  await expect(dialog).toBeHidden();
  await expect(deleteAccountButton).toBeFocused();
  await expect(page.getByText("Ada Lovelace")).toBeVisible();
  await page.reload();
  await expect(page.getByText("Ada Lovelace")).toBeVisible();

  await deleteAccountButton.click();
  await expect(dialog).toBeVisible();
  await cancelButton.click();

  await expect(dialog).toBeHidden();
  await expect(deleteAccountButton).toBeFocused();
  await expect(page.getByText("Ada Lovelace")).toBeVisible();
  await page.reload();
  await expect(page.getByText("Ada Lovelace")).toBeVisible();
});

test("deletes the account and keeps it deleted after reload", async ({ page }) => {
  const deleteAccountButton = page.getByRole("button", { name: "Delete account", exact: true, includeHidden: true });
  const confirmInput = page.getByLabel("Type DELETE to confirm");
  const confirmButton = page.getByRole("button", { name: "Delete my account", exact: true });
  const deletedStatus = page.getByRole("status");
  const deleteRequests = [];

  page.on("request", (request) => {
    const url = new URL(request.url());
    if (request.method() === "DELETE" && url.pathname === "/api/account") {
      deleteRequests.push(request);
    }
  });

  await deleteAccountButton.click();
  await confirmInput.fill("DELETE");

  const deleteResponse = page.waitForResponse((response) => {
    const url = new URL(response.url());
    return response.request().method() === "DELETE" && url.pathname === "/api/account";
  });
  await confirmButton.click();
  await expect(deletedStatus).toHaveText("Your account has been deleted");

  await expect.poll(() => deleteRequests.length).toBe(1);
  expect((await deleteResponse).status()).toBe(200);

  await page.reload();
  await expect(deletedStatus).toHaveText("Your account has been deleted");
  await expect(deleteAccountButton).toBeHidden();
});
