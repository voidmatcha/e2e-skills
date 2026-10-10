import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  await page.request.post("/api/reset");
  await page.goto("/");
});

test("updates the header avatar initials while typing the display name", async ({ page }) => {
  const displayNameInput = page.getByLabel("Display name");
  const avatar = page.getByRole("img", { name: /^Avatar$/ });

  await displayNameInput.fill("Ada Lovelace");
  await expect(avatar).toHaveText("AL");

  await displayNameInput.fill("Grace");
  await expect(avatar).toHaveText("G");
});

test("saves the display name and restores it after reload", async ({ page }) => {
  const displayNameInput = page.getByLabel("Display name");
  const saveButton = page.getByRole("button", { name: /^Save$/ });

  await displayNameInput.fill("Grace Hopper");
  const saveRequest = page.waitForRequest(
    (request) => request.method() === "PUT" && new URL(request.url()).pathname === "/api/profile",
  );
  const saveResponse = page.waitForResponse(
    (response) => response.request().method() === "PUT" && new URL(response.url()).pathname === "/api/profile",
  );
  await saveButton.click();

  const request = await saveRequest;
  expect(request.postDataJSON()).toEqual({ displayName: "Grace Hopper" });
  expect((await saveResponse).status()).toBe(200);
  await expect(page.getByRole("status")).toHaveText("Profile saved");
  await expect(page.getByText("Grace Hopper")).toBeVisible();

  await page.reload();

  await expect(displayNameInput).toHaveValue("Grace Hopper");
  await expect(page.getByText("Grace Hopper")).toBeVisible();
});

test("refuses display names outside the allowed length without storing them", async ({ page }) => {
  const displayNameInput = page.getByLabel("Display name");
  const saveButton = page.getByRole("button", { name: /^Save$/ });
  const error = page.getByRole("alert");

  await expect(displayNameInput).toHaveValue("Ada Lovelace");

  await displayNameInput.fill("A");
  await saveButton.click();
  await expect(error).toHaveText("Name must be 2–30 characters");

  await page.reload();
  await expect(displayNameInput).toHaveValue("Ada Lovelace");
  await expect(page.getByText("Ada Lovelace")).toBeVisible();

  await displayNameInput.fill("A very long display name over thirty");
  await saveButton.click();
  await expect(error).toHaveText("Name must be 2–30 characters");

  await page.reload();
  await expect(displayNameInput).toHaveValue("Ada Lovelace");
  await expect(page.getByText("Ada Lovelace")).toBeVisible();
});
