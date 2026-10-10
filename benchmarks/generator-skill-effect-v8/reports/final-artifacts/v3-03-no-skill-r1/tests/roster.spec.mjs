import { expect, test } from "@playwright/test";

test.beforeEach(async ({ request }) => {
  await request.post("/api/reset");
});

const memberRow = (page, name) => page.locator("tr.member").filter({ hasText: name });

test("shows the full roster with the initial leave count", async ({ page }) => {
  await page.goto("/");

  await expect(page.locator("#tr-headcount")).toHaveText("5 members · 1 on leave");
  await expect(page.getByRole("row")).toHaveCount(6);

  await expect(memberRow(page, "Ada Lovelace")).toContainText("Ada LovelaceEngineerActive");
  await expect(memberRow(page, "Grace Hopper")).toContainText("Grace HopperLeadActive");
  await expect(memberRow(page, "Linus Torvalds")).toContainText("Linus TorvaldsEngineerOn leave");
  await expect(memberRow(page, "Margaret Hamilton")).toContainText("Margaret HamiltonManagerActive");
  await expect(memberRow(page, "Ken Thompson")).toContainText("Ken ThompsonEngineerActive");
});

test("toggles leave status and keeps it after reload", async ({ page }) => {
  await page.goto("/");

  await memberRow(page, "Ada Lovelace").getByRole("button", { name: "Toggle leave for Ada Lovelace" }).click();

  await expect(memberRow(page, "Ada Lovelace")).toContainText("On leave");
  await expect(page.locator("#tr-headcount")).toHaveText("5 members · 2 on leave");

  await page.reload();

  await expect(memberRow(page, "Ada Lovelace")).toContainText("On leave");
  await expect(page.locator("#tr-headcount")).toHaveText("5 members · 2 on leave");
});

test("cancels an inline removal confirmation without changing the roster", async ({ page }) => {
  await page.goto("/");

  await memberRow(page, "Ada Lovelace").getByRole("button", { name: "Remove Ada Lovelace" }).click();

  const confirmRow = page.getByRole("row").filter({ hasText: "Remove Ada?" });
  await expect(confirmRow).toBeVisible();

  await confirmRow.getByRole("button", { name: "Cancel removing Ada Lovelace" }).click();

  await expect(confirmRow).toBeHidden();
  await expect(memberRow(page, "Ada Lovelace")).toBeVisible();
  await expect(page.locator("#tr-headcount")).toHaveText("5 members · 1 on leave");
});

test("confirms removal of one member and keeps it after reload", async ({ page }) => {
  await page.goto("/");

  await memberRow(page, "Ada Lovelace").getByRole("button", { name: "Remove Ada Lovelace" }).click();
  await page.getByRole("row").filter({ hasText: "Remove Ada?" }).getByRole("button", { name: "Confirm removing Ada Lovelace" }).click();

  await expect(memberRow(page, "Ada Lovelace")).toHaveCount(0);
  await expect(memberRow(page, "Grace Hopper")).toBeVisible();
  await expect(memberRow(page, "Linus Torvalds")).toBeVisible();
  await expect(memberRow(page, "Margaret Hamilton")).toBeVisible();
  await expect(memberRow(page, "Ken Thompson")).toBeVisible();
  await expect(page.locator("#tr-headcount")).toHaveText("4 members · 1 on leave");

  await page.reload();

  await expect(memberRow(page, "Ada Lovelace")).toHaveCount(0);
  await expect(page.locator("#tr-headcount")).toHaveText("4 members · 1 on leave");
});
