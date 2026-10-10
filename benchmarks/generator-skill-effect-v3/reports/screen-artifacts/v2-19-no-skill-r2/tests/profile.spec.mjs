import { expect, test } from "@playwright/test";

const TOO_SHORT_OR_LONG = "Name must be 2–30 characters";

test.beforeEach(async ({ page, request }) => {
  await request.post("/api/reset");
  await page.goto("/");
  await expect(page.locator("#pf-header-name")).toHaveText("Ada Lovelace");
});

const nameField = (page) => page.getByLabel("Display name");
const save = (page) => page.getByRole("button", { name: "Save" });

test("avatar initials update live while typing", async ({ page }) => {
  const avatar = page.getByRole("img", { name: "Avatar" });
  await nameField(page).fill("Grace Hopper");
  await expect(avatar).toHaveText("GH");
  await nameField(page).fill("Grace");
  await expect(avatar).toHaveText("G");
  await nameField(page).fill("ada lovelace");
  await expect(avatar).toHaveText("AL");
});

test("typing does not change the header name until saved", async ({ page }) => {
  await nameField(page).fill("Grace Hopper");
  await expect(page.locator("#pf-header-name")).toHaveText("Ada Lovelace");
});

test("save stores the name and it persists after reload", async ({ page }) => {
  await nameField(page).fill("Grace Hopper");
  await save(page).click();
  await expect(page.getByRole("status")).toHaveText("Profile saved");
  await expect(page.locator("#pf-header-name")).toHaveText("Grace Hopper");
  await expect(page.getByRole("alert")).toHaveText("");

  await page.reload();
  await expect(nameField(page)).toHaveValue("Grace Hopper");
  await expect(page.locator("#pf-header-name")).toHaveText("Grace Hopper");
  await expect(page.getByRole("img", { name: "Avatar" })).toHaveText("GH");
});

for (const [label, value] of [
  ["empty", ""],
  ["one character", "A"],
  ["31 characters", "a".repeat(31)],
]) {
  test(`refuses a name that is ${label} and stores nothing`, async ({ page, request }) => {
    await nameField(page).fill(value);
    await save(page).click();
    await expect(page.getByRole("alert")).toHaveText(TOO_SHORT_OR_LONG);
    await expect(page.getByRole("status")).toHaveText("");
    await expect(page.locator("#pf-header-name")).toHaveText("Ada Lovelace");

    const stored = await (await request.get("/api/profile")).json();
    expect(stored.displayName).toBe("Ada Lovelace");
    await page.reload();
    await expect(nameField(page)).toHaveValue("Ada Lovelace");
  });
}

for (const [label, value] of [
  ["2 characters", "Al"],
  ["30 characters", "a".repeat(30)],
]) {
  test(`accepts a name of exactly ${label}`, async ({ page }) => {
    await nameField(page).fill(value);
    await save(page).click();
    await expect(page.getByRole("status")).toHaveText("Profile saved");
    await expect(page.getByRole("alert")).toHaveText("");
    await page.reload();
    await expect(nameField(page)).toHaveValue(value);
  });
}
