import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page, request }) => {
  // State lives on the server, so restore the seeded roster before each test.
  const res = await request.post("/api/reset");
  expect(res.ok()).toBeTruthy();
  await page.goto("/");
  await expect(page.locator("#tr-rows tr.member")).toHaveCount(5);
});

const headcount = (page) => page.locator("#tr-headcount");
const memberRow = (page, name) => page.locator("tr.member", { hasText: name });

test("shows five members with Linus on leave", async ({ page }) => {
  await expect(headcount(page)).toHaveText("5 members · 1 on leave");
  await expect(memberRow(page, "Ada Lovelace").locator(".badge")).toHaveText("Active");
  await expect(memberRow(page, "Linus Torvalds").locator(".badge")).toHaveText("On leave");
});

test("toggle leave switches the badge and headcount both ways", async ({ page }) => {
  const ada = memberRow(page, "Ada Lovelace");
  await page.getByRole("button", { name: "Toggle leave for Ada Lovelace" }).click();
  await expect(ada.locator(".badge")).toHaveText("On leave");
  await expect(headcount(page)).toHaveText("5 members · 2 on leave");

  await page.getByRole("button", { name: "Toggle leave for Ada Lovelace" }).click();
  await expect(ada.locator(".badge")).toHaveText("Active");
  await expect(headcount(page)).toHaveText("5 members · 1 on leave");
});

test("returning Linus from leave updates the headcount", async ({ page }) => {
  await page.getByRole("button", { name: "Toggle leave for Linus Torvalds" }).click();
  await expect(memberRow(page, "Linus Torvalds").locator(".badge")).toHaveText("Active");
  await expect(headcount(page)).toHaveText("5 members · 0 on leave");
});

test("leave status survives a reload", async ({ page }) => {
  await page.getByRole("button", { name: "Toggle leave for Ada Lovelace" }).click();
  await page.getByRole("button", { name: "Toggle leave for Linus Torvalds" }).click();
  await expect(headcount(page)).toHaveText("5 members · 1 on leave");

  await page.reload();
  await expect(page.locator("#tr-rows tr.member")).toHaveCount(5);
  await expect(memberRow(page, "Ada Lovelace").locator(".badge")).toHaveText("On leave");
  await expect(memberRow(page, "Linus Torvalds").locator(".badge")).toHaveText("Active");
  await expect(headcount(page)).toHaveText("5 members · 1 on leave");
});

test("remove opens an inline confirmation under that member", async ({ page }) => {
  await page.getByRole("button", { name: "Remove Grace Hopper" }).click();
  const confirm = page.locator("tr.confirm");
  await expect(confirm).toHaveCount(1);
  await expect(confirm).toContainText("Remove Grace?");
  await expect(confirm.getByRole("button", { name: "Confirm removing Grace Hopper" })).toBeVisible();
  await expect(confirm.getByRole("button", { name: "Cancel removing Grace Hopper" })).toBeVisible();
  // The confirmation row sits directly after Grace's row.
  await expect(page.locator("tr.member", { hasText: "Grace Hopper" }).locator("+ tr")).toHaveClass("confirm");
});

test("cancel keeps the member and closes the confirmation", async ({ page }) => {
  await page.getByRole("button", { name: "Remove Ada Lovelace" }).click();
  await page.getByRole("button", { name: "Cancel removing Ada Lovelace" }).click();
  await expect(page.locator("tr.confirm")).toHaveCount(0);
  await expect(memberRow(page, "Ada Lovelace")).toBeVisible();
  await expect(headcount(page)).toHaveText("5 members · 1 on leave");

  await page.reload();
  await expect(page.locator("#tr-rows tr.member")).toHaveCount(5);
});

test("confirm removes exactly that member and survives a reload", async ({ page }) => {
  await page.getByRole("button", { name: "Remove Ada Lovelace" }).click();
  await expect(page.locator("tr.confirm")).toContainText("Remove Ada?");
  await page.getByRole("button", { name: "Confirm removing Ada Lovelace" }).click();

  const check = async () => {
    await expect(page.locator("tr.confirm")).toHaveCount(0);
    await expect(page.locator("#tr-rows tr.member")).toHaveCount(4);
    await expect(memberRow(page, "Ada Lovelace")).toHaveCount(0);
    for (const name of ["Grace Hopper", "Linus Torvalds", "Margaret Hamilton", "Ken Thompson"]) {
      await expect(memberRow(page, name)).toBeVisible();
    }
    await expect(headcount(page)).toHaveText("4 members · 1 on leave");
  };
  await check();
  await page.reload();
  await check();
});

test("removing a member on leave lowers the on-leave count", async ({ page }) => {
  await page.getByRole("button", { name: "Remove Linus Torvalds" }).click();
  await page.getByRole("button", { name: "Confirm removing Linus Torvalds" }).click();
  await expect(headcount(page)).toHaveText("4 members · 0 on leave");
  await expect(memberRow(page, "Linus Torvalds")).toHaveCount(0);
});
