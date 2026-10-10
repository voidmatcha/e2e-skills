import { expect, test } from "@playwright/test";

const memberRow = (page, name) =>
  page.getByRole("row").filter({
    has: page.getByRole("cell", { name }),
  });

const expectHeadcount = async (page, text) => {
  await expect(page.getByText(text, { exact: true })).toBeVisible();
};

test.beforeEach(async ({ page, request }) => {
  await request.post("/api/reset");
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Team roster", exact: true })).toBeVisible();
  await expectHeadcount(page, "5 members · 1 on leave");
});

test("shows seeded members with Linus on leave", async ({ page }) => {
  await expect(memberRow(page, "Ada Lovelace")).toContainText("Active");
  await expect(memberRow(page, "Grace Hopper")).toContainText("Active");
  await expect(memberRow(page, "Linus Torvalds")).toContainText("On leave");
  await expect(memberRow(page, "Margaret Hamilton")).toContainText("Active");
  await expect(memberRow(page, "Ken Thompson")).toContainText("Active");
});

test("toggles leave status and persists it after reload", async ({ page }) => {
  const patch = page.waitForRequest((request) => {
    if (request.method() !== "PATCH") return false;
    const url = new URL(request.url());
    return url.pathname === "/api/members/1";
  });

  await page.getByRole("button", { name: "Toggle leave for Ada Lovelace", exact: true }).click();

  const request = await patch;
  expect(request.postDataJSON()).toEqual({ onLeave: true });
  await expect(memberRow(page, "Ada Lovelace")).toContainText("On leave");
  await expectHeadcount(page, "5 members · 2 on leave");

  await page.reload();
  await expect(memberRow(page, "Ada Lovelace")).toContainText("On leave");
  await expectHeadcount(page, "5 members · 2 on leave");
});

test("cancels removal without changing the roster", async ({ page }) => {
  await page.getByRole("button", { name: "Remove Ada Lovelace", exact: true }).click();
  await expect(page.getByText("Remove Ada?", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: "Cancel removing Ada Lovelace", exact: true }).click();

  await expect(page.getByText("Remove Ada?", { exact: true })).not.toBeVisible();
  await expect(memberRow(page, "Ada Lovelace")).toBeVisible();
  await expectHeadcount(page, "5 members · 1 on leave");
});

test("confirms removal of exactly one member and persists it after reload", async ({ page }) => {
  await page.getByRole("button", { name: "Remove Ada Lovelace", exact: true }).click();
  await expect(page.getByText("Remove Ada?", { exact: true })).toBeVisible();

  const remove = page.waitForRequest((request) => {
    if (request.method() !== "DELETE") return false;
    const url = new URL(request.url());
    return url.pathname === "/api/members/1";
  });

  await page.getByRole("button", { name: "Confirm removing Ada Lovelace", exact: true }).click();
  await remove;

  await expect(memberRow(page, "Ada Lovelace")).toHaveCount(0);
  await expect(memberRow(page, "Grace Hopper")).toBeVisible();
  await expect(memberRow(page, "Linus Torvalds")).toBeVisible();
  await expect(memberRow(page, "Margaret Hamilton")).toBeVisible();
  await expect(memberRow(page, "Ken Thompson")).toBeVisible();
  await expectHeadcount(page, "4 members · 1 on leave");

  await page.reload();
  await expect(memberRow(page, "Ada Lovelace")).toHaveCount(0);
  await expectHeadcount(page, "4 members · 1 on leave");
});
