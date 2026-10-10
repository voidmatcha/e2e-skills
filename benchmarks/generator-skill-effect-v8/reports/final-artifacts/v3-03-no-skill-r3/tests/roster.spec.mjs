import { expect, test } from "@playwright/test";

const members = [
  ["Ada Lovelace", "Engineer", "Active"],
  ["Grace Hopper", "Lead", "Active"],
  ["Linus Torvalds", "Engineer", "On leave"],
  ["Margaret Hamilton", "Manager", "Active"],
  ["Ken Thompson", "Engineer", "Active"],
];

test.beforeEach(async ({ request }) => {
  await request.post("/api/reset");
});

test("shows the seeded team roster and headcount", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByText("5 members · 1 on leave")).toBeVisible();
  await expect(page.locator("tbody tr.member")).toHaveCount(5);

  for (const [name, role, status] of members) {
    const row = page.getByRole("row", { name: new RegExp(`${name} ${role} ${status}`) });
    await expect(row).toBeVisible();
    await expect(row.getByRole("button", { name: `Toggle leave for ${name}` })).toBeVisible();
    await expect(row.getByRole("button", { name: `Remove ${name}` })).toBeVisible();
  }
});

test("toggles leave status and keeps it after reload", async ({ page }) => {
  await page.goto("/");

  await page.getByRole("button", { name: "Toggle leave for Ada Lovelace" }).click();
  await expect(page.getByRole("row", { name: /Ada Lovelace Engineer On leave/ })).toBeVisible();
  await expect(page.getByText("5 members · 2 on leave")).toBeVisible();

  await page.getByRole("button", { name: "Toggle leave for Linus Torvalds" }).click();
  await expect(page.getByRole("row", { name: /Linus Torvalds Engineer Active/ })).toBeVisible();
  await expect(page.getByText("5 members · 1 on leave")).toBeVisible();

  await page.reload();

  await expect(page.getByRole("row", { name: /Ada Lovelace Engineer On leave/ })).toBeVisible();
  await expect(page.getByRole("row", { name: /Linus Torvalds Engineer Active/ })).toBeVisible();
  await expect(page.getByText("5 members · 1 on leave")).toBeVisible();
});

test("cancels and confirms inline removal", async ({ page }) => {
  await page.goto("/");

  await page.getByRole("button", { name: "Remove Ada Lovelace" }).click();

  const rowsWithConfirmation = page.locator("tbody tr");
  await expect(rowsWithConfirmation).toHaveCount(6);
  await expect(rowsWithConfirmation.nth(0)).toContainText("Ada Lovelace");
  await expect(rowsWithConfirmation.nth(1)).toContainText("Remove Ada?");
  await expect(rowsWithConfirmation.nth(1).getByRole("button", { name: "Confirm removing Ada Lovelace" })).toBeVisible();
  await expect(rowsWithConfirmation.nth(1).getByRole("button", { name: "Cancel removing Ada Lovelace" })).toBeVisible();

  await page.getByRole("button", { name: "Cancel removing Ada Lovelace" }).click();
  await expect(page.locator("tbody tr")).toHaveCount(5);
  await expect(page.getByRole("row", { name: /Ada Lovelace Engineer Active/ })).toBeVisible();
  await expect(page.getByText("5 members · 1 on leave")).toBeVisible();

  await page.getByRole("button", { name: "Remove Grace Hopper" }).click();
  await expect(page.getByText("Remove Grace?")).toBeVisible();
  await page.getByRole("button", { name: "Confirm removing Grace Hopper" }).click();

  await expect(page.locator("tbody tr.member")).toHaveCount(4);
  await expect(page.getByRole("row", { name: /Grace Hopper/ })).toHaveCount(0);
  await expect(page.getByRole("row", { name: /Ada Lovelace Engineer Active/ })).toBeVisible();
  await expect(page.getByRole("row", { name: /Linus Torvalds Engineer On leave/ })).toBeVisible();
  await expect(page.getByText("4 members · 1 on leave")).toBeVisible();

  await page.reload();

  await expect(page.locator("tbody tr.member")).toHaveCount(4);
  await expect(page.getByRole("row", { name: /Grace Hopper/ })).toHaveCount(0);
  await expect(page.getByText("4 members · 1 on leave")).toBeVisible();
});
