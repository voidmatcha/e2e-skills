import { expect, test } from "@playwright/test";

const memberNames = [
  "Ada Lovelace",
  "Grace Hopper",
  "Linus Torvalds",
  "Margaret Hamilton",
  "Ken Thompson",
];

const memberRow = (page, name) =>
  page.getByRole("row").filter({
    has: page.getByRole("cell", { name, exact: true }),
  });

test.beforeEach(async ({ page }) => {
  await page.request.post("/api/reset");
  await page.goto("/");
});

test("shows the seeded team roster", async ({ page }) => {
  await expect(page.getByText("5 members · 1 on leave")).toBeVisible();
  await expect(page.getByRole("row")).toHaveCount(6);

  for (const name of memberNames) {
    await expect(memberRow(page, name)).toBeVisible();
  }

  await expect(memberRow(page, "Linus Torvalds").getByRole("cell", { name: "On leave" })).toBeVisible();
});

test("toggles a member leave status and persists it", async ({ page }) => {
  const adaRow = memberRow(page, "Ada Lovelace");
  const leaveUpdate = page.waitForRequest((request) => {
    if (request.method() !== "PATCH" || !request.url().includes("/api/members/")) {
      return false;
    }

    return request.postDataJSON().onLeave === true;
  });

  await adaRow.getByRole("button", { name: "Toggle leave for Ada Lovelace" }).click();
  await leaveUpdate;

  await expect(adaRow.getByRole("cell", { name: "On leave" })).toBeVisible();
  await expect(page.getByText("5 members · 2 on leave")).toBeVisible();

  await page.reload();
  await expect(memberRow(page, "Ada Lovelace").getByRole("cell", { name: "On leave" })).toBeVisible();
  await expect(page.getByText("5 members · 2 on leave")).toBeVisible();
});

test("cancels and confirms removing exactly one member", async ({ page }) => {
  const adaRow = memberRow(page, "Ada Lovelace");

  await adaRow.getByRole("button", { name: "Remove Ada Lovelace" }).click();
  await expect(page.getByText("Remove Ada?")).toBeVisible();

  await page.getByRole("button", { name: "Cancel removing Ada Lovelace", exact: true }).click();
  await expect(page.getByRole("button", { name: "Confirm removing Ada Lovelace", exact: true })).toHaveCount(0);
  await expect(adaRow).toBeVisible();
  await expect(page.getByText("5 members · 1 on leave")).toBeVisible();

  const removal = page.waitForRequest((request) =>
    request.method() === "DELETE" && request.url().includes("/api/members/"),
  );

  await adaRow.getByRole("button", { name: "Remove Ada Lovelace" }).click();
  await page.getByRole("button", { name: "Confirm removing Ada Lovelace", exact: true }).click();
  await removal;

  await expect(memberRow(page, "Ada Lovelace")).toHaveCount(0);
  await expect(page.getByText("4 members · 1 on leave")).toBeVisible();

  for (const name of memberNames.filter((memberName) => memberName !== "Ada Lovelace")) {
    await expect(memberRow(page, name)).toBeVisible();
  }

  await page.reload();
  await expect(memberRow(page, "Ada Lovelace")).toHaveCount(0);
  await expect(page.getByText("4 members · 1 on leave")).toBeVisible();
});
