import { expect, test } from "@playwright/test";

const defaultName = "Ada Lovelace";
const savedName = "Grace Hopper";
const errorMessage = "Name must be 2–30 characters";

test.beforeEach(async ({ page }) => {
  const response = await page.request.post("/api/reset");
  expect(response.ok()).toBeTruthy();
});

test("updates the header avatar initials while typing", async ({ page }) => {
  await page.goto("/");

  const displayNameInput = page.getByLabel("Display name");
  const avatar = page.getByRole("img", { name: "Avatar", exact: true });

  await expect(displayNameInput).toHaveValue(defaultName);
  await expect(avatar).toHaveText("AL");

  await displayNameInput.fill(savedName);
  await expect(avatar).toHaveText("GH");

  await displayNameInput.fill("Grace");
  await expect(avatar).toHaveText("G");
});

test("saves the display name and reloads the stored profile", async ({ page }) => {
  await page.goto("/");

  const displayNameInput = page.getByLabel("Display name");
  const saveButton = page.getByRole("button", { name: "Save", exact: true });
  const avatar = page.getByRole("img", { name: "Avatar", exact: true });
  const savedStatus = page.getByRole("status");

  await displayNameInput.fill(savedName);
  const requestPromise = page.waitForRequest(
    (request) => request.method() === "PUT" && new URL(request.url()).pathname === "/api/profile",
  );
  await saveButton.click();
  const request = await requestPromise;

  expect(request.postDataJSON()).toEqual({ displayName: savedName });
  await expect(savedStatus).toHaveText("Profile saved");
  await expect(page.getByText(savedName)).toBeVisible();
  await expect(avatar).toHaveText("GH");

  await page.reload();
  await expect(displayNameInput).toHaveValue(savedName);
  await expect(page.getByText(savedName)).toBeVisible();
});

for (const { title, invalidName } of [
  { title: "shorter than 2 characters", invalidName: "A" },
  { title: "longer than 30 characters", invalidName: "A".repeat(31) },
]) {
  test(`refuses a display name ${title}`, async ({ page }) => {
    await page.goto("/");

    const displayNameInput = page.getByLabel("Display name");
    const saveButton = page.getByRole("button", { name: "Save", exact: true });
    const alert = page.getByRole("alert");

    await expect(displayNameInput).toHaveValue(defaultName);
    await displayNameInput.fill(invalidName);
    await saveButton.click();

    await expect(alert).toHaveText(errorMessage);
    await expect(page.getByRole("status")).toBeEmpty();

    await page.reload();
    await expect(displayNameInput).toHaveValue(defaultName);
    await expect(page.getByText(defaultName)).toBeVisible();
  });
}
