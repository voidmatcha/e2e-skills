import { expect, test } from "@playwright/test";

const ERROR = "Name must be 2–30 characters";

test.beforeEach(async ({ page, request }) => {
  const res = await request.post("/api/reset");
  expect(res.ok()).toBeTruthy();
  await page.goto("/");
  await expect(page.getByLabel("Display name")).toHaveValue("Ada Lovelace");
});

test("avatar initials update live as the name is typed", async ({ page }) => {
  const name = page.getByLabel("Display name");
  const avatar = page.locator("#pf-avatar");
  await expect(avatar).toHaveText("AL");

  await name.fill("Grace");
  await expect(avatar).toHaveText("G");

  await name.fill("");
  await expect(avatar).toHaveText("");

  await name.pressSequentially("Grace Hopper");
  await expect(avatar).toHaveText("GH");

  // header name is unchanged until Save
  await expect(page.locator("#pf-header-name")).toHaveText("Ada Lovelace");
});

test("save stores the name and updates the header, persisting across reload", async ({ page }) => {
  const name = page.getByLabel("Display name");
  await name.fill("Grace Hopper");
  await page.getByRole("button", { name: "Save" }).click();

  await expect(page.getByRole("status")).toHaveText("Profile saved");
  await expect(page.locator("#pf-header-name")).toHaveText("Grace Hopper");
  await expect(page.locator("#pf-avatar")).toHaveText("GH");

  await page.reload();
  await expect(name).toHaveValue("Grace Hopper");
  await expect(page.locator("#pf-header-name")).toHaveText("Grace Hopper");
  await expect(page.locator("#pf-avatar")).toHaveText("GH");
});

for (const [label, value] of [
  ["empty", ""],
  ["1 character", "A"],
  ["31 characters", "a".repeat(31)],
]) {
  test(`refuses a name of ${label} and stores nothing`, async ({ page, request }) => {
    await page.getByLabel("Display name").fill(value);
    await page.getByRole("button", { name: "Save" }).click();

    await expect(page.getByRole("alert")).toHaveText(ERROR);
    await expect(page.getByRole("status")).toHaveText("");
    await expect(page.locator("#pf-header-name")).toHaveText("Ada Lovelace");

    const stored = await (await request.get("/api/profile")).json();
    expect(stored.displayName).toBe("Ada Lovelace");

    await page.reload();
    await expect(page.getByLabel("Display name")).toHaveValue("Ada Lovelace");
    await expect(page.locator("#pf-header-name")).toHaveText("Ada Lovelace");
  });
}

for (const [label, value] of [
  ["2 characters", "Al"],
  ["30 characters", "a".repeat(30)],
]) {
  test(`accepts a name of ${label}`, async ({ page }) => {
    await page.getByLabel("Display name").fill(value);
    await page.getByRole("button", { name: "Save" }).click();

    await expect(page.getByRole("status")).toHaveText("Profile saved");
    await expect(page.getByRole("alert")).toHaveText("");
    await expect(page.locator("#pf-header-name")).toHaveText(value);
  });
}
