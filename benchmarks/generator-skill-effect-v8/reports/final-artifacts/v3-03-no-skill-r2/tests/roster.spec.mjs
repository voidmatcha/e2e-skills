import { expect, test } from "@playwright/test";

const members = [
  "Ada Lovelace",
  "Grace Hopper",
  "Linus Torvalds",
  "Margaret Hamilton",
  "Ken Thompson",
];

const memberRow = (page, name) =>
  page.locator("tr.member").filter({ has: page.getByRole("cell", { name, exact: true }) });

const headcount = (page) => page.locator("#tr-headcount");

test.beforeEach(async ({ request }) => {
  await request.post("/api/reset");
});

test("shows the full roster with Linus on leave", async ({ page }) => {
  await page.goto("/");

  await expect(headcount(page)).toHaveText("5 members · 1 on leave");
  await expect(page.locator("tr.member")).toHaveCount(5);

  for (const name of members) {
    await expect(memberRow(page, name)).toBeVisible();
  }

  await expect(memberRow(page, "Ada Lovelace").getByText("Active")).toBeVisible();
  await expect(memberRow(page, "Linus Torvalds").getByText("On leave")).toBeVisible();
});

test("toggles leave status and keeps it after reload", async ({ page }) => {
  await page.goto("/");

  await memberRow(page, "Ada Lovelace").getByRole("button", { name: "Toggle leave for Ada Lovelace" }).click();

  await expect(memberRow(page, "Ada Lovelace").getByText("On leave")).toBeVisible();
  await expect(headcount(page)).toHaveText("5 members · 2 on leave");

  await page.reload();

  await expect(memberRow(page, "Ada Lovelace").getByText("On leave")).toBeVisible();
  await expect(headcount(page)).toHaveText("5 members · 2 on leave");

  await memberRow(page, "Ada Lovelace").getByRole("button", { name: "Toggle leave for Ada Lovelace" }).click();

  await expect(memberRow(page, "Ada Lovelace").getByText("Active")).toBeVisible();
  await expect(headcount(page)).toHaveText("5 members · 1 on leave");
});

test("cancels and confirms removing a member", async ({ page }) => {
  await page.goto("/");

  await memberRow(page, "Ada Lovelace").getByRole("button", { name: "Remove Ada Lovelace" }).click();

  const confirmation = page.locator("tr.confirm").filter({ hasText: "Remove Ada?" });
  await expect(confirmation).toBeVisible();
  await expect(memberRow(page, "Ada Lovelace").locator("xpath=following-sibling::tr[1]")).toContainText("Remove Ada?");

  await confirmation.getByRole("button", { name: "Cancel removing Ada Lovelace" }).click();

  await expect(confirmation).toBeHidden();
  await expect(memberRow(page, "Ada Lovelace")).toBeVisible();
  await expect(headcount(page)).toHaveText("5 members · 1 on leave");

  await memberRow(page, "Ada Lovelace").getByRole("button", { name: "Remove Ada Lovelace" }).click();
  await page
    .locator("tr.confirm")
    .filter({ hasText: "Remove Ada?" })
    .getByRole("button", { name: "Confirm removing Ada Lovelace" })
    .click();

  await expect(memberRow(page, "Ada Lovelace")).toHaveCount(0);
  await expect(memberRow(page, "Grace Hopper")).toBeVisible();
  await expect(memberRow(page, "Linus Torvalds")).toBeVisible();
  await expect(memberRow(page, "Margaret Hamilton")).toBeVisible();
  await expect(memberRow(page, "Ken Thompson")).toBeVisible();
  await expect(page.locator("tr.member")).toHaveCount(4);
  await expect(headcount(page)).toHaveText("4 members · 1 on leave");

  await page.reload();

  await expect(memberRow(page, "Ada Lovelace")).toHaveCount(0);
  await expect(page.locator("tr.member")).toHaveCount(4);
  await expect(headcount(page)).toHaveText("4 members · 1 on leave");
});
