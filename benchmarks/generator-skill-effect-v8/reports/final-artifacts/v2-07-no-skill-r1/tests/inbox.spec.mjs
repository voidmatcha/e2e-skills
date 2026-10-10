import { expect, test } from "@playwright/test";

test.beforeEach(async ({ request }) => {
  await request.post("/api/reset");
});

test("opens one unread message, updates only its read state, and persists after reload", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByRole("heading", { name: "Inbox (3)" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Open unread Lunch on Friday?" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Open unread Compiler notes" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Open Patch review" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Open unread Launch checklist" })).toBeVisible();

  await page.getByRole("button", { name: "Open unread Lunch on Friday?" }).click();

  await expect(page.getByRole("heading", { name: "Inbox (2)" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Lunch on Friday?" })).toBeVisible();
  await expect(page.getByRole("article", { name: "Message" }).getByText("From Ada")).toBeVisible();
  await expect(
    page.getByRole("article", { name: "Message" }).getByText("Shall we try the new place by the river?"),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "Open Lunch on Friday?" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Open unread Lunch on Friday?" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Open unread Compiler notes" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Open Patch review" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Open unread Launch checklist" })).toBeVisible();

  await page.reload();

  await expect(page.getByRole("heading", { name: "Inbox (2)" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Open Lunch on Friday?" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Open unread Lunch on Friday?" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Open unread Compiler notes" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Open Patch review" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Open unread Launch checklist" })).toBeVisible();
});

test("filters unread messages and marks all messages read", async ({ page }) => {
  await page.goto("/");

  await page.getByLabel("Unread only").check();

  await expect(page.getByRole("heading", { name: "Inbox (3)" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Open unread Lunch on Friday?" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Open unread Compiler notes" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Open Patch review" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Open unread Launch checklist" })).toBeVisible();

  await page.getByLabel("Unread only").uncheck();
  await page.getByRole("button", { name: "Mark all read" }).click();

  await expect(page.getByRole("heading", { name: "Inbox (0)" })).toBeVisible();
  await expect(page.getByRole("button", { name: /^Open unread / })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Open Lunch on Friday?" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Open Compiler notes" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Open Patch review" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Open Launch checklist" })).toBeVisible();

  await page.getByLabel("Unread only").check();

  await expect(page.getByRole("list", { name: "Messages" }).getByRole("button")).toHaveCount(0);
});
