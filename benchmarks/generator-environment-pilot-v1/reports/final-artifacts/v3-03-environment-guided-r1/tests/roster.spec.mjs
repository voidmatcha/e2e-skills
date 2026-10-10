import { expect, test } from "@playwright/test";

const memberRow = (page, name) => page.getByRole("row").filter({ hasText: name });
const headcount = (page) => page.getByText(/^\d+ members? · \d+ on leave$/);

test.beforeEach(async ({ page, request }) => {
  await request.post("/api/reset");
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Team roster", exact: true })).toBeVisible();
});

test("shows the seeded roster and leave headcount", async ({ page }) => {
  await expect(headcount(page)).toHaveText("5 members · 1 on leave");

  await expect(memberRow(page, "Ada Lovelace")).toContainText("Active");
  await expect(memberRow(page, "Grace Hopper")).toContainText("Active");
  await expect(memberRow(page, "Linus Torvalds")).toContainText("On leave");
  await expect(memberRow(page, "Margaret Hamilton")).toContainText("Active");
  await expect(memberRow(page, "Ken Thompson")).toContainText("Active");
});

test("toggles leave status and keeps it after reload", async ({ page }) => {
  const leaveUpdate = page.waitForRequest((request) =>
    request.method() === "PATCH" &&
    request.url().endsWith("/api/members/1") &&
    request.postDataJSON().onLeave === true
  );

  await page.getByRole("button", { name: "Toggle leave for Ada Lovelace", exact: true }).click();
  await leaveUpdate;

  await expect(memberRow(page, "Ada Lovelace")).toContainText("On leave");
  await expect(headcount(page)).toHaveText("5 members · 2 on leave");

  await page.reload();
  await expect(memberRow(page, "Ada Lovelace")).toContainText("On leave");
  await expect(headcount(page)).toHaveText("5 members · 2 on leave");
});

test("cancels an inline removal confirmation", async ({ page }) => {
  await page.getByRole("button", { name: "Remove Ada Lovelace", exact: true }).click();
  await expect(page.getByText("Remove Ada?")).toBeVisible();

  await page.getByRole("button", { name: "Cancel removing Ada Lovelace", exact: true }).click();

  await expect(page.getByText("Remove Ada?")).not.toBeVisible();
  await expect(memberRow(page, "Ada Lovelace")).toBeVisible();
  await expect(headcount(page)).toHaveText("5 members · 1 on leave");
});

test("confirms removal of exactly one member and keeps it after reload", async ({ page }) => {
  await page.getByRole("button", { name: "Remove Ada Lovelace", exact: true }).click();
  await expect(page.getByText("Remove Ada?")).toBeVisible();

  const removal = page.waitForRequest((request) =>
    request.method() === "DELETE" && request.url().endsWith("/api/members/1")
  );
  await page.getByRole("button", { name: "Confirm removing Ada Lovelace", exact: true }).click();
  await removal;

  await expect(memberRow(page, "Grace Hopper")).toBeVisible();
  await expect(memberRow(page, "Linus Torvalds")).toContainText("On leave");
  await expect(memberRow(page, "Margaret Hamilton")).toBeVisible();
  await expect(memberRow(page, "Ken Thompson")).toBeVisible();
  await expect(headcount(page)).toHaveText("4 members · 1 on leave");

  await page.reload();
  await expect(memberRow(page, "Ada Lovelace")).toHaveCount(0);
  await expect(headcount(page)).toHaveText("4 members · 1 on leave");
});
