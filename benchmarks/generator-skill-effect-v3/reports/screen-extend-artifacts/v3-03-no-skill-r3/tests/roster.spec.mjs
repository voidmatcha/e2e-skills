import { expect, test } from "@playwright/test";

const memberRow = (page, name) =>
  page.getByRole("row").filter({ has: page.getByRole("cell", { name, exact: true }) });

test.beforeEach(async ({ page, request }) => {
  const res = await request.post("/api/reset");
  expect(res.ok()).toBeTruthy();
  await page.goto("/");
  await expect(page.locator("#tr-headcount")).toHaveText("5 members · 1 on leave");
});

test("lists the five seeded members with their status", async ({ page }) => {
  await expect(page.locator("#tr-rows tr.member")).toHaveCount(5);
  await expect(memberRow(page, "Ada Lovelace").locator(".badge")).toHaveText("Active");
  await expect(memberRow(page, "Linus Torvalds").locator(".badge")).toHaveText("On leave");
});

test("toggle leave switches the badge and headcount both ways", async ({ page }) => {
  const headcount = page.locator("#tr-headcount");
  const ada = memberRow(page, "Ada Lovelace");

  await page.getByRole("button", { name: "Toggle leave for Ada Lovelace" }).click();
  await expect(ada.locator(".badge")).toHaveText("On leave");
  await expect(headcount).toHaveText("5 members · 2 on leave");

  await page.getByRole("button", { name: "Toggle leave for Ada Lovelace" }).click();
  await expect(ada.locator(".badge")).toHaveText("Active");
  await expect(headcount).toHaveText("5 members · 1 on leave");

  await page.getByRole("button", { name: "Toggle leave for Linus Torvalds" }).click();
  await expect(memberRow(page, "Linus Torvalds").locator(".badge")).toHaveText("Active");
  await expect(headcount).toHaveText("5 members · 0 on leave");
});

test("leave status survives a reload", async ({ page }) => {
  await page.getByRole("button", { name: "Toggle leave for Grace Hopper" }).click();
  await expect(page.locator("#tr-headcount")).toHaveText("5 members · 2 on leave");
  await page.reload();
  await expect(page.locator("#tr-headcount")).toHaveText("5 members · 2 on leave");
  await expect(memberRow(page, "Grace Hopper").locator(".badge")).toHaveText("On leave");
});

test("remove opens an inline confirmation under that member", async ({ page }) => {
  await page.getByRole("button", { name: "Remove Ada Lovelace" }).click();
  const confirm = page.locator("tr.confirm");
  await expect(confirm).toHaveCount(1);
  await expect(confirm).toContainText("Remove Ada?");
  await expect(confirm.getByRole("button", { name: /^Confirm/ })).toBeVisible();
  await expect(confirm.getByRole("button", { name: /^Cancel/ })).toBeVisible();
  // the confirmation row sits directly beneath Ada's row
  await expect(page.locator("tr.member").first().locator("xpath=following-sibling::tr[1]")).toHaveClass("confirm");
});

test("cancel keeps the member and closes the row", async ({ page }) => {
  await page.getByRole("button", { name: "Remove Ada Lovelace" }).click();
  await page.getByRole("button", { name: "Cancel removing Ada Lovelace" }).click();
  await expect(page.locator("tr.confirm")).toHaveCount(0);
  await expect(memberRow(page, "Ada Lovelace")).toHaveCount(1);
  await expect(page.locator("#tr-headcount")).toHaveText("5 members · 1 on leave");
  await page.reload();
  await expect(page.locator("#tr-rows tr.member")).toHaveCount(5);
});

test("confirm removes exactly that member and persists after reload", async ({ page }) => {
  await page.getByRole("button", { name: "Remove Grace Hopper" }).click();
  await expect(page.locator("tr.confirm")).toContainText("Remove Grace?");
  await page.getByRole("button", { name: "Confirm removing Grace Hopper" }).click();

  await expect(page.locator("tr.confirm")).toHaveCount(0);
  await expect(page.locator("#tr-rows tr.member")).toHaveCount(4);
  await expect(memberRow(page, "Grace Hopper")).toHaveCount(0);
  for (const name of ["Ada Lovelace", "Linus Torvalds", "Margaret Hamilton", "Ken Thompson"]) {
    await expect(memberRow(page, name)).toHaveCount(1);
  }
  await expect(page.locator("#tr-headcount")).toHaveText("4 members · 1 on leave");

  await page.reload();
  await expect(page.locator("#tr-headcount")).toHaveText("4 members · 1 on leave");
  await expect(memberRow(page, "Grace Hopper")).toHaveCount(0);
});

test("removing a member on leave lowers the on-leave count", async ({ page }) => {
  await page.getByRole("button", { name: "Remove Linus Torvalds" }).click();
  await page.getByRole("button", { name: "Confirm removing Linus Torvalds" }).click();
  await expect(page.locator("#tr-headcount")).toHaveText("4 members · 0 on leave");
});
