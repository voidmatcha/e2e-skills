import { expect, test } from "@playwright/test";

test.beforeEach(async ({ request }) => {
  await request.post("/api/reset");
});

test("updates initials while typing and persists a saved display name", async ({ page }) => {
  await page.goto("/");

  const name = page.getByLabel("Display name");
  const avatar = page.getByRole("img", { name: "Avatar" });
  const headerName = page.locator("#pf-header-name");

  await expect(name).toHaveValue("Ada Lovelace");
  await expect(headerName).toHaveText("Ada Lovelace");
  await expect(avatar).toHaveText("AL");

  await name.fill("Grace");
  await expect(avatar).toHaveText("G");
  await expect(headerName).toHaveText("Ada Lovelace");

  await name.fill("Ada Lovelace");
  await expect(avatar).toHaveText("AL");

  await name.fill("Grace Hopper");
  await page.getByRole("button", { name: "Save" }).click();

  await expect(page.getByRole("status")).toHaveText("Profile saved");
  await expect(headerName).toHaveText("Grace Hopper");
  await expect(avatar).toHaveText("GH");

  await page.reload();
  await expect(name).toHaveValue("Grace Hopper");
  await expect(headerName).toHaveText("Grace Hopper");
  await expect(avatar).toHaveText("GH");
});

test("refuses display names outside the allowed length", async ({ page }) => {
  await page.goto("/");

  const name = page.getByLabel("Display name");
  const error = page.getByRole("alert");
  const status = page.getByRole("status");
  const save = page.getByRole("button", { name: "Save" });

  await expect(name).toHaveValue("Ada Lovelace");

  await name.fill("A");
  await save.click();
  await expect(error).toHaveText("Name must be 2–30 characters");
  await expect(status).toBeEmpty();

  await page.reload();
  await expect(name).toHaveValue("Ada Lovelace");
  await expect(page.locator("#pf-header-name")).toHaveText("Ada Lovelace");

  await name.fill("A".repeat(31));
  await save.click();
  await expect(error).toHaveText("Name must be 2–30 characters");
  await expect(status).toBeEmpty();

  await page.reload();
  await expect(name).toHaveValue("Ada Lovelace");
  await expect(page.locator("#pf-header-name")).toHaveText("Ada Lovelace");
});
