import { expect, test } from "@playwright/test";

test.beforeEach(async ({ request }) => {
  await request.post("/api/reset");
});

test("opens an unread message and only marks that message read", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByRole("heading", { name: "Inbox (3)" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Open unread Lunch on Friday?" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Open unread Compiler notes" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Open Patch review" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Open unread Launch checklist" })).toBeVisible();

  await page.getByRole("button", { name: "Open unread Compiler notes" }).click();

  const reader = page.getByRole("article", { name: "Message" });
  await expect(page.getByRole("heading", { name: "Compiler notes" })).toBeVisible();
  await expect(reader.getByText("From Grace")).toBeVisible();
  await expect(reader.getByText("Attached are the notes from yesterday's session.")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Inbox (2)" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Open Compiler notes" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Open unread Lunch on Friday?" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Open unread Launch checklist" })).toBeVisible();
});

test("marks all messages read and clears unread markers", async ({ page }) => {
  await page.goto("/");

  await page.getByRole("button", { name: "Mark all read" }).click();

  await expect(page.getByRole("heading", { name: "Inbox (0)" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Open Lunch on Friday?" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Open Compiler notes" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Open Patch review" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Open Launch checklist" })).toBeVisible();
  await expect(page.getByRole("button", { name: /Open unread/ })).toHaveCount(0);
});

test("unread only filter hides read messages", async ({ page }) => {
  await page.goto("/");

  await page.getByLabel("Unread only").check();

  await expect(page.getByRole("button", { name: "Open unread Lunch on Friday?" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Open unread Compiler notes" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Open unread Launch checklist" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Open Patch review" })).toHaveCount(0);
});

test("reload preserves server-side read state", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Open unread Lunch on Friday?" }).click();

  await expect(page.getByRole("heading", { name: "Inbox (2)" })).toBeVisible();

  await page.reload();

  await expect(page.getByRole("heading", { name: "Inbox (2)" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Open Lunch on Friday?" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Open unread Compiler notes" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Open Patch review" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Open unread Launch checklist" })).toBeVisible();
});
