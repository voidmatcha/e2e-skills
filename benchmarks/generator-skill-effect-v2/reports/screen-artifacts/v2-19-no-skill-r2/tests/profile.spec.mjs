import { expect, test } from "@playwright/test";

const ERROR = "Name must be 2–30 characters";

test.beforeEach(async ({ page, request }) => {
  await request.post("/api/reset");
  await page.goto("/");
  await expect(page.getByLabel("Display name")).toHaveValue("Ada Lovelace");
});

test("initials update live as the name is typed", async ({ page }) => {
  const name = page.getByLabel("Display name");
  const avatar = page.locator("#pf-avatar");
  await name.fill("Grace");
  await expect(avatar).toHaveText("G");
  await name.fill("Grace Hopper");
  await expect(avatar).toHaveText("GH");
  await name.fill("Ada Lovelace");
  await expect(avatar).toHaveText("AL");
});

test("save stores the name and updates the header, which survives reload", async ({ page }) => {
  const name = page.getByLabel("Display name");
  await name.fill("Grace Hopper");
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("status")).toHaveText("Profile saved");
  await expect(page.locator("#pf-header-name")).toHaveText("Grace Hopper");

  await page.reload();
  await expect(name).toHaveValue("Grace Hopper");
  await expect(page.locator("#pf-header-name")).toHaveText("Grace Hopper");
  await expect(page.locator("#pf-avatar")).toHaveText("GH");
});

for (const [label, value] of [
  ["1 character", "A"],
  ["31 characters", "A".repeat(31)],
]) {
  test(`refuses a name of ${label} and stores nothing`, async ({ page, request }) => {
    await page.getByLabel("Display name").fill(value);
    await page.getByRole("button", { name: "Save" }).click();
    await expect(page.getByRole("alert")).toHaveText(ERROR);
    await expect(page.getByRole("status")).toBeEmpty();
    await expect(page.locator("#pf-header-name")).toHaveText("Ada Lovelace");

    const stored = await (await request.get("/api/profile")).json();
    expect(stored.displayName).toBe("Ada Lovelace");
    await page.reload();
    await expect(page.getByLabel("Display name")).toHaveValue("Ada Lovelace");
  });
}

for (const [label, value] of [
  ["2 characters", "Al"],
  ["30 characters", "B".repeat(30)],
]) {
  test(`accepts a name of ${label}`, async ({ page, request }) => {
    await page.getByLabel("Display name").fill(value);
    await page.getByRole("button", { name: "Save" }).click();
    await expect(page.getByRole("status")).toHaveText("Profile saved");
    await expect(page.getByRole("alert")).toBeEmpty();
    const stored = await (await request.get("/api/profile")).json();
    expect(stored.displayName).toBe(value);
  });
}
