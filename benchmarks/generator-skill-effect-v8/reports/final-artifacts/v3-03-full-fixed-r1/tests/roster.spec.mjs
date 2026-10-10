import { expect, test } from "@playwright/test";

const members = [
  ["Ada Lovelace", "Engineer", "Active"],
  ["Grace Hopper", "Lead", "Active"],
  ["Linus Torvalds", "Engineer", "On leave"],
  ["Margaret Hamilton", "Manager", "Active"],
  ["Ken Thompson", "Engineer", "Active"],
];

const memberRow = (page, name) =>
  page.getByRole("row").filter({
    has: page.getByRole("cell", { name: new RegExp(`^${name}$`) }),
  });

test.beforeEach(async ({ page, request }) => {
  await request.post("/api/reset");
  await page.goto("/");
  await expect(page.getByText("5 members · 1 on leave")).toBeVisible();
});

test("shows the seeded roster and leave count", async ({ page }) => {
  await expect(
    page.getByRole("row").filter({
      has: page.getByRole("button", { name: /^Toggle leave for / }),
    }),
  ).toHaveCount(5);

  for (const [name, role, status] of members) {
    const row = memberRow(page, name);
    await expect(row.getByRole("cell", { name, exact: true })).toBeVisible();
    await expect(row.getByRole("cell", { name: role, exact: true })).toBeVisible();
    await expect(row.getByRole("cell", { name: status, exact: true })).toBeVisible();
  }
});

test("toggles a member leave status and persists it after reload", async ({ page }) => {
  const linusRow = memberRow(page, "Linus Torvalds");
  const toggleLeave = page.getByRole("button", { name: "Toggle leave for Linus Torvalds" });
  const toggleRequest = page.waitForRequest((request) => {
    if (request.method() !== "PATCH") return false;
    if (new URL(request.url()).pathname !== "/api/members/3") return false;
    return request.postDataJSON().onLeave === false;
  });

  await toggleLeave.click();
  await toggleRequest;

  await expect(linusRow).toContainText("Active");
  await expect(page.getByText("5 members · 0 on leave")).toBeVisible();

  await page.reload();
  await expect(memberRow(page, "Linus Torvalds")).toContainText("Active");
  await expect(page.getByText("5 members · 0 on leave")).toBeVisible();
});

test("cancels and confirms removing a member with persisted headcount", async ({ page }) => {
  const adaRow = memberRow(page, "Ada Lovelace");

  await page.getByRole("button", { name: "Remove Ada Lovelace" }).click();
  await expect(page.getByText("Remove Ada?")).toBeVisible();

  await page.getByRole("button", { name: "Cancel removing Ada Lovelace" }).click();
  await expect(page.getByText("Remove Ada?")).not.toBeVisible();
  await expect(adaRow).toBeVisible();
  await expect(page.getByText("5 members · 1 on leave")).toBeVisible();

  await page.getByRole("button", { name: "Remove Ada Lovelace" }).click();
  await expect(page.getByText("Remove Ada?")).toBeVisible();

  const deleteRequest = page.waitForRequest(
    (request) => request.method() === "DELETE" && new URL(request.url()).pathname === "/api/members/1",
  );
  await page.getByRole("button", { name: "Confirm removing Ada Lovelace" }).click();
  await deleteRequest;

  await expect(adaRow).not.toBeAttached();
  await expect(page.getByText("4 members · 1 on leave")).toBeVisible();

  await page.reload();
  await expect(memberRow(page, "Ada Lovelace")).not.toBeAttached();
  await expect(page.getByText("4 members · 1 on leave")).toBeVisible();
});
