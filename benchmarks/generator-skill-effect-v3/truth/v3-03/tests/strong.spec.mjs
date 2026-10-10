import { expect, test } from "@playwright/test";

const rowOf = (page, name) => page.getByRole("row", { name: new RegExp(name) });
const headcount = (page) => page.getByText(/^\d+ members? · \d+ on leave$/);

test.beforeEach(async ({ page }) => {
  await page.request.post("/api/reset");
  await page.goto("/");
  await expect(headcount(page)).toHaveText("5 members · 1 on leave");
});

test("toggle leave flips the badge and the headcount, and persists", async ({ page }) => {
  await expect(rowOf(page, "Ada Lovelace")).toContainText("Active");
  await page.getByRole("button", { name: "Toggle leave for Ada Lovelace" }).click();
  await expect(rowOf(page, "Ada Lovelace")).toContainText("On leave");
  await expect(headcount(page)).toHaveText("5 members · 2 on leave");
  await page.getByRole("button", { name: "Toggle leave for Linus Torvalds" }).click();
  await expect(rowOf(page, "Linus Torvalds")).toContainText("Active");
  await expect(headcount(page)).toHaveText("5 members · 1 on leave");
  await page.reload();
  await expect(rowOf(page, "Ada Lovelace")).toContainText("On leave");
  await expect(rowOf(page, "Linus Torvalds")).toContainText("Active");
  await expect(headcount(page)).toHaveText("5 members · 1 on leave");
});

test("cancel keeps the member, confirm removes exactly that member", async ({ page }) => {
  await page.getByRole("button", { name: "Remove Grace Hopper" }).click();
  await expect(page.getByText("Remove Grace?")).toBeVisible();
  await page.getByRole("button", { name: "Cancel removing Grace Hopper" }).click();
  await expect(page.getByText("Remove Grace?")).toBeHidden();
  await expect(rowOf(page, "Grace Hopper")).toBeVisible();
  await expect(headcount(page)).toHaveText("5 members · 1 on leave");
  await page.getByRole("button", { name: "Remove Grace Hopper" }).click();
  await page.getByRole("button", { name: "Confirm removing Grace Hopper" }).click();
  await expect(rowOf(page, "Grace Hopper")).toHaveCount(0);
  await expect(rowOf(page, "Ada Lovelace")).toBeVisible();
  await expect(page.getByRole("row")).toHaveCount(5);
  await expect(headcount(page)).toHaveText("4 members · 1 on leave");
  await page.reload();
  await expect(rowOf(page, "Grace Hopper")).toHaveCount(0);
  await expect(headcount(page)).toHaveText("4 members · 1 on leave");
});
