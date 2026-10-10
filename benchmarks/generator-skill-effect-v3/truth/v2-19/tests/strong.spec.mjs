import { expect, test } from "@playwright/test";

const name = (page) => page.getByLabel("Display name");
const avatar = (page) => page.getByRole("img", { name: "Avatar" });
const header = (page) => page.locator("header");

test.beforeEach(async ({ page }) => {
  await page.request.post("/api/reset");
  await page.goto("/");
  await expect(name(page)).toHaveValue("Ada Lovelace");
  await expect(avatar(page)).toHaveText("AL");
});

test("initials follow the name as it is typed", async ({ page }) => {
  await name(page).fill("Grace Brewster Hopper");
  await expect(avatar(page)).toHaveText("GH");
  await name(page).fill("Grace");
  await expect(avatar(page)).toHaveText("G");
  await expect(header(page)).toContainText("Ada Lovelace");
});

test("save stores the name and the header follows", async ({ page }) => {
  await name(page).fill("Grace Hopper");
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("status")).toHaveText("Profile saved");
  await expect(header(page)).toContainText("Grace Hopper");
  await page.reload();
  await expect(name(page)).toHaveValue("Grace Hopper");
  await expect(header(page)).toContainText("Grace Hopper");
  await expect(avatar(page)).toHaveText("GH");
});

test("names outside 2 to 30 characters are refused", async ({ page }) => {
  await name(page).fill("A");
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("alert")).toHaveText("Name must be 2–30 characters");
  await name(page).fill("x".repeat(31));
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("alert")).toHaveText("Name must be 2–30 characters");
  await page.reload();
  await expect(name(page)).toHaveValue("Ada Lovelace");
  await name(page).fill("y".repeat(30));
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("status")).toHaveText("Profile saved");
});
