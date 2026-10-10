import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page, request }) => {
  await request.post("/api/reset");
  await page.goto("/");
  await expect(page.getByRole("row")).toHaveCount(6);
});

const member = (page, name) => page.getByRole("row", { name: new RegExp(name) }).first();
const headcount = (page) => page.locator("#tr-headcount");

test("shows five members with Linus on leave", async ({ page }) => {
  await expect(headcount(page)).toHaveText("5 members · 1 on leave");
  await expect(member(page, "Linus Torvalds").locator(".badge")).toHaveText("On leave");
  await expect(member(page, "Ada Lovelace").locator(".badge")).toHaveText("Active");
});

test("toggle leave switches badge and headcount, and survives reload", async ({ page }) => {
  await page.getByRole("button", { name: "Toggle leave for Ada Lovelace" }).click();
  await expect(member(page, "Ada Lovelace").locator(".badge")).toHaveText("On leave");
  await expect(headcount(page)).toHaveText("5 members · 2 on leave");

  await page.reload();
  await expect(member(page, "Ada Lovelace").locator(".badge")).toHaveText("On leave");
  await expect(headcount(page)).toHaveText("5 members · 2 on leave");

  await page.getByRole("button", { name: "Toggle leave for Ada Lovelace" }).click();
  await page.getByRole("button", { name: "Toggle leave for Linus Torvalds" }).click();
  await expect(member(page, "Ada Lovelace").locator(".badge")).toHaveText("Active");
  await expect(member(page, "Linus Torvalds").locator(".badge")).toHaveText("Active");
  await expect(headcount(page)).toHaveText("5 members · 0 on leave");
  await page.reload();
  await expect(headcount(page)).toHaveText("5 members · 0 on leave");
});

test("remove opens an inline confirmation under that member", async ({ page }) => {
  await page.getByRole("button", { name: "Remove Ada Lovelace" }).click();
  await expect(page.getByText("Remove Ada?")).toBeVisible();
  await expect(page.getByRole("row")).toHaveCount(7);
  const rows = page.locator("#tr-rows tr");
  await expect(rows.nth(0)).toContainText("Ada Lovelace");
  await expect(rows.nth(1)).toContainText("Remove Ada?");
});

test("cancel keeps the member and closes the confirmation", async ({ page }) => {
  await page.getByRole("button", { name: "Remove Ada Lovelace" }).click();
  await page.getByRole("button", { name: "Cancel removing Ada Lovelace" }).click();
  await expect(page.getByText("Remove Ada?")).toHaveCount(0);
  await expect(member(page, "Ada Lovelace")).toBeVisible();
  await expect(headcount(page)).toHaveText("5 members · 1 on leave");
  await page.reload();
  await expect(member(page, "Ada Lovelace")).toBeVisible();
});

test("confirm removes exactly that member and persists after reload", async ({ page }) => {
  await page.getByRole("button", { name: "Remove Grace Hopper" }).click();
  await expect(page.getByText("Remove Grace?")).toBeVisible();
  await page.getByRole("button", { name: "Confirm removing Grace Hopper" }).click();

  const check = async () => {
    await expect(page.getByRole("cell", { name: "Grace Hopper", exact: true })).toHaveCount(0);
    for (const n of ["Ada Lovelace", "Linus Torvalds", "Margaret Hamilton", "Ken Thompson"]) {
      await expect(page.getByRole("cell", { name: n, exact: true })).toBeVisible();
    }
    await expect(page.getByText("Remove Grace?")).toHaveCount(0);
    await expect(headcount(page)).toHaveText("4 members · 1 on leave");
  };
  await check();
  await page.reload();
  await check();
});

test("removing an on-leave member updates the on-leave count", async ({ page }) => {
  await page.getByRole("button", { name: "Remove Linus Torvalds" }).click();
  await page.getByRole("button", { name: "Confirm removing Linus Torvalds" }).click();
  await expect(headcount(page)).toHaveText("4 members · 0 on leave");
  await page.reload();
  await expect(headcount(page)).toHaveText("4 members · 0 on leave");
});
