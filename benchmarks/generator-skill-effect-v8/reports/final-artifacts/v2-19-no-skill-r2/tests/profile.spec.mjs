import { expect, test } from "@playwright/test";

test.beforeEach(async ({ request }) => {
  await request.post("/api/reset");
});

test("updates header initials as the display name is typed", async ({ page }) => {
  await page.goto("/");

  const name = page.getByLabel("Display name");
  const avatar = page.getByRole("img", { name: "Avatar" });

  await name.fill("Ada Lovelace");
  await expect(avatar).toHaveText("AL");

  await name.fill("Grace");
  await expect(avatar).toHaveText("G");
});

test("saves the display name and shows it after reload", async ({ page }) => {
  await page.goto("/");

  await page.getByLabel("Display name").fill("Grace Hopper");
  await page.getByRole("button", { name: "Save" }).click();

  await expect(page.getByRole("status")).toHaveText("Profile saved");
  await expect(page.locator("#pf-header-name")).toHaveText("Grace Hopper");

  await page.reload();

  await expect(page.getByLabel("Display name")).toHaveValue("Grace Hopper");
  await expect(page.locator("#pf-header-name")).toHaveText("Grace Hopper");
});

test("refuses display names shorter than 2 or longer than 30 characters", async ({ page }) => {
  await page.goto("/");

  const name = page.getByLabel("Display name");
  const save = page.getByRole("button", { name: "Save" });

  await name.fill("Grace Hopper");
  await save.click();
  await expect(page.getByRole("status")).toHaveText("Profile saved");

  await name.fill("G");
  await save.click();
  await expect(page.getByRole("alert")).toHaveText("Name must be 2–30 characters");

  await page.reload();
  await expect(page.getByLabel("Display name")).toHaveValue("Grace Hopper");
  await expect(page.locator("#pf-header-name")).toHaveText("Grace Hopper");

  await name.fill("A name that is definitely too long");
  await save.click();
  await expect(page.getByRole("alert")).toHaveText("Name must be 2–30 characters");

  await page.reload();
  await expect(page.getByLabel("Display name")).toHaveValue("Grace Hopper");
  await expect(page.locator("#pf-header-name")).toHaveText("Grace Hopper");
});
