import { expect, test } from "@playwright/test";

const ERROR = "Name must be 2–30 characters";

test.beforeEach(async ({ page, request }) => {
  await request.post("/api/reset");
  await page.goto("/");
  // Wait for the initial profile fetch so it cannot overwrite what we type.
  await expect(page.getByLabel("Display name")).toHaveValue("Ada Lovelace");
});

const field = (page) => page.getByLabel("Display name");
const avatar = (page) => page.getByRole("img", { name: "Avatar" });
const headerName = (page) => page.locator("#pf-header-name");
const save = (page) => page.getByRole("button", { name: "Save" });

test("initial profile shows name and initials in the header", async ({ page }) => {
  await expect(headerName(page)).toHaveText("Ada Lovelace");
  await expect(avatar(page)).toHaveText("AL");
});

test("avatar initials update live while typing", async ({ page }) => {
  await field(page).fill("");
  await field(page).pressSequentially("Grace");
  await expect(avatar(page)).toHaveText("G");
  await field(page).pressSequentially(" Hopper");
  await expect(avatar(page)).toHaveText("GH");
  // Typing alone does not change the header name.
  await expect(headerName(page)).toHaveText("Ada Lovelace");
});

test("a single word gives its first letter only", async ({ page }) => {
  await field(page).fill("Grace");
  await expect(avatar(page)).toHaveText("G");
});

test("save stores the name, confirms, and persists across reload", async ({ page }) => {
  await field(page).fill("Grace Hopper");
  await save(page).click();
  await expect(page.getByRole("status")).toHaveText("Profile saved");
  await expect(headerName(page)).toHaveText("Grace Hopper");
  await expect(avatar(page)).toHaveText("GH");

  await page.reload();
  await expect(field(page)).toHaveValue("Grace Hopper");
  await expect(headerName(page)).toHaveText("Grace Hopper");
  await expect(avatar(page)).toHaveText("GH");
});

for (const [label, name] of [
  ["empty", ""],
  ["1 character", "A"],
  ["31 characters", "a".repeat(31)],
]) {
  test(`refuses a name that is ${label} and stores nothing`, async ({ page }) => {
    await field(page).fill(name);
    await save(page).click();
    await expect(page.getByRole("alert")).toHaveText(ERROR);
    await expect(page.getByRole("status")).toHaveText("");
    await expect(headerName(page)).toHaveText("Ada Lovelace");

    await page.reload();
    await expect(field(page)).toHaveValue("Ada Lovelace");
    await expect(headerName(page)).toHaveText("Ada Lovelace");
  });
}

for (const [label, name] of [
  ["2 characters", "Al"],
  ["30 characters", "a".repeat(30)],
]) {
  test(`accepts a name of ${label}`, async ({ page }) => {
    await field(page).fill(name);
    await save(page).click();
    await expect(page.getByRole("status")).toHaveText("Profile saved");
    await expect(page.getByRole("alert")).toHaveText("");
    await page.reload();
    await expect(field(page)).toHaveValue(name);
  });
}
