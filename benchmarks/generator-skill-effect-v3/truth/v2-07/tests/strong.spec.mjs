import { expect, test } from "@playwright/test";

const heading = (page) => page.getByRole("heading", { level: 1 });
const rows = (page) => page.getByRole("list", { name: "Messages" }).getByRole("listitem");

test.beforeEach(async ({ page }) => {
  await page.request.post("/api/reset");
  await page.goto("/");
  await expect(heading(page)).toHaveText("Inbox (3)");
});

test("opening a message shows it and marks only it read", async ({ page }) => {
  await page.getByRole("button", { name: "Open unread Compiler notes" }).click();
  const reader = page.getByRole("article", { name: "Message" });
  await expect(reader.getByRole("heading")).toHaveText("Compiler notes");
  await expect(reader).toContainText("From Grace");
  await expect(reader).toContainText("Attached are the notes");
  await expect(heading(page)).toHaveText("Inbox (2)");
  await expect(page.getByRole("button", { name: "Open Compiler notes" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Open unread Lunch on Friday?" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Open unread Launch checklist" })).toBeVisible();
});

test("read state survives a reload", async ({ page }) => {
  await page.getByRole("button", { name: "Open unread Lunch on Friday?" }).click();
  await expect(heading(page)).toHaveText("Inbox (2)");
  await page.reload();
  await expect(heading(page)).toHaveText("Inbox (2)");
  await expect(page.getByRole("button", { name: "Open Lunch on Friday?" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Open unread Compiler notes" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Open unread Launch checklist" })).toBeVisible();
});

test("mark all read clears the count and markers", async ({ page }) => {
  await page.getByRole("button", { name: "Mark all read" }).click();
  await expect(heading(page)).toHaveText("Inbox (0)");
  await expect(page.getByRole("button", { name: /Open unread/ })).toHaveCount(0);
  await page.reload();
  await expect(heading(page)).toHaveText("Inbox (0)");
});

test("the unread filter hides messages read in this session too", async ({ page }) => {
  await page.getByLabel("Unread only").check();
  await expect(rows(page)).toHaveCount(3);
  await page.getByRole("button", { name: "Open unread Launch checklist" }).click();
  await expect(rows(page)).toHaveCount(2);
  await expect(page.getByRole("list", { name: "Messages" })).not.toContainText("Launch checklist");
  await page.getByLabel("Unread only").uncheck();
  await expect(rows(page)).toHaveCount(4);
});
