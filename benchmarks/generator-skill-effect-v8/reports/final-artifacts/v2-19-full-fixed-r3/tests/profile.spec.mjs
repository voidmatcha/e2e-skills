import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page, request }) => {
  await request.post("/api/reset");
  await page.goto("/");
  await expect(page.getByLabel("Display name")).toHaveValue("Ada Lovelace");
});

test("updates the header avatar initials while the display name is edited", async ({ page }) => {
  const displayName = page.getByLabel("Display name");
  const avatar = page.getByRole("img", { name: "Avatar", exact: true });

  await displayName.fill("Ada Lovelace");
  await expect(avatar).toHaveText("AL");

  await displayName.fill("Grace");
  await expect(avatar).toHaveText("G");
});

test("saves the display name and restores it after reload", async ({ page }) => {
  const displayName = page.getByLabel("Display name");
  const saveButton = page.getByRole("button", { name: "Save", exact: true });

  await displayName.fill("Grace Hopper");
  const saveRequest = page.waitForRequest(
    (request) => request.method() === "PUT" && new URL(request.url()).pathname === "/api/profile",
  );
  await saveButton.click();
  const request = await saveRequest;

  expect(request.postDataJSON()).toEqual({ displayName: "Grace Hopper" });
  await expect(page.getByRole("status")).toHaveText("Profile saved");
  await expect(page.getByText("Grace Hopper")).toBeVisible();

  await page.reload();
  await expect(displayName).toHaveValue("Grace Hopper");
  await expect(page.getByText("Grace Hopper")).toBeVisible();
});

test("refuses display names outside the allowed length without storing them", async ({ page }) => {
  const displayName = page.getByLabel("Display name");
  const saveButton = page.getByRole("button", { name: "Save", exact: true });
  const error = page.getByRole("alert");
  const saveRequests = [];

  await page.route("**/api/profile", async (route) => {
    if (route.request().method() === "PUT") saveRequests.push(route.request().postDataJSON());
    await route.continue();
  });

  for (const invalidName of ["A", "A".repeat(31)]) {
    await displayName.fill(invalidName);
    await saveButton.click();
    await expect(error).toHaveText("Name must be 2\u201330 characters");
    expect(saveRequests).toHaveLength(0);

    await page.reload();
    await expect(displayName).toHaveValue("Ada Lovelace");
    await expect(page.getByText("Ada Lovelace")).toBeVisible();
  }
});
