import { expect, test } from "@playwright/test";

const ERROR = "Name must be 2–30 characters";

test.beforeEach(async ({ page, request }) => {
  const res = await request.post("/api/reset");
  expect(res.ok()).toBeTruthy();
  await page.goto("/");
  await expect(page.getByLabel("Display name")).toHaveValue("Ada Lovelace");
});

const avatar = (page) => page.locator("#pf-avatar");
const headerName = (page) => page.locator("#pf-header-name");

test("loads the stored name into the field and header", async ({ page }) => {
  await expect(headerName(page)).toHaveText("Ada Lovelace");
  await expect(avatar(page)).toHaveText("AL");
});

test("avatar initials update live while typing", async ({ page }) => {
  const field = page.getByLabel("Display name");
  await field.fill("Grace Hopper");
  await expect(avatar(page)).toHaveText("GH");
  await field.fill("Grace");
  await expect(avatar(page)).toHaveText("G");
  await field.fill("Ada Lovelace");
  await expect(avatar(page)).toHaveText("AL");
});

test("typing alone does not change the header name", async ({ page }) => {
  await page.getByLabel("Display name").fill("Grace");
  await expect(headerName(page)).toHaveText("Ada Lovelace");
});

test("save stores the name, confirms, and updates the header", async ({ page }) => {
  await page.getByLabel("Display name").fill("Grace Hopper");
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("status")).toHaveText("Profile saved");
  await expect(headerName(page)).toHaveText("Grace Hopper");
  await expect(avatar(page)).toHaveText("GH");
  await expect(page.getByRole("alert")).toHaveText("");
});

test("saved name persists across reload", async ({ page }) => {
  await page.getByLabel("Display name").fill("Grace");
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("status")).toHaveText("Profile saved");

  await page.reload();
  await expect(page.getByLabel("Display name")).toHaveValue("Grace");
  await expect(headerName(page)).toHaveText("Grace");
  await expect(avatar(page)).toHaveText("G");
});

for (const [label, name] of [
  ["empty", ""],
  ["1 character", "A"],
  ["31 characters", "a".repeat(31)],
]) {
  test(`refuses a ${label} name and stores nothing`, async ({ page, request }) => {
    await page.getByLabel("Display name").fill(name);
    await page.getByRole("button", { name: "Save" }).click();
    await expect(page.getByRole("alert")).toHaveText(ERROR);
    await expect(page.getByRole("status")).toHaveText("");
    await expect(headerName(page)).toHaveText("Ada Lovelace");

    const stored = await (await request.get("/api/profile")).json();
    expect(stored.displayName).toBe("Ada Lovelace");

    await page.reload();
    await expect(page.getByLabel("Display name")).toHaveValue("Ada Lovelace");
    await expect(headerName(page)).toHaveText("Ada Lovelace");
  });
}

for (const [label, name] of [
  ["2 characters", "Bo"],
  ["30 characters", "a".repeat(30)],
]) {
  test(`accepts a ${label} name`, async ({ page }) => {
    await page.getByLabel("Display name").fill(name);
    await page.getByRole("button", { name: "Save" }).click();
    await expect(page.getByRole("status")).toHaveText("Profile saved");
    await expect(page.getByRole("alert")).toHaveText("");
    await expect(headerName(page)).toHaveText(name);
  });
}

test("a valid save clears a previous error", async ({ page }) => {
  const field = page.getByLabel("Display name");
  await field.fill("A");
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("alert")).toHaveText(ERROR);
  await field.fill("Alan");
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("status")).toHaveText("Profile saved");
  await expect(page.getByRole("alert")).toHaveText("");
});
