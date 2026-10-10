import { expect, test } from "@playwright/test";

const profile = (page) => ({
  avatar: page.getByRole("img", { name: "Avatar" }),
  nameInput: page.getByLabel("Display name"),
  saveButton: page.getByRole("button", { name: "Save" }),
  status: page.getByRole("status"),
  error: page.getByRole("alert"),
  headerName: page.locator("#pf-header-name"),
});

test.beforeEach(async ({ request }) => {
  await request.post("/api/reset");
});

test("updates header avatar initials as the display name is typed", async ({ page }) => {
  const { avatar, nameInput } = profile(page);

  await page.goto("/");
  await nameInput.fill("");
  await nameInput.fill("Ada Lovelace");
  await expect(avatar).toHaveText("AL");

  await nameInput.fill("Grace");
  await expect(avatar).toHaveText("G");
});

test("saves the display name and restores it after reload", async ({ page }) => {
  const { headerName, nameInput, saveButton, status } = profile(page);

  await page.goto("/");
  await nameInput.fill("Grace Hopper");
  await saveButton.click();

  await expect(status).toHaveText("Profile saved");
  await expect(headerName).toHaveText("Grace Hopper");

  await page.reload();
  await expect(nameInput).toHaveValue("Grace Hopper");
  await expect(headerName).toHaveText("Grace Hopper");
});

for (const displayName of ["A", "ABCDEFGHIJKLMNOPQRSTUVWXYZABCDE"]) {
  test(`refuses to save invalid display name "${displayName}"`, async ({ page }) => {
    const { error, headerName, nameInput, saveButton, status } = profile(page);

    await page.goto("/");
    await expect(nameInput).toHaveValue("Ada Lovelace");

    await nameInput.fill(displayName);
    await saveButton.click();

    await expect(error).toHaveText("Name must be 2–30 characters");
    await expect(status).toBeEmpty();
    await expect(headerName).toHaveText("Ada Lovelace");

    await page.reload();
    await expect(nameInput).toHaveValue("Ada Lovelace");
    await expect(headerName).toHaveText("Ada Lovelace");
  });
}
