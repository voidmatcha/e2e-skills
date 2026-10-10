import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page, request }) => {
  const res = await request.post("/api/reset");
  expect(res.ok()).toBeTruthy();
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Inbox (3)" })).toBeVisible();
});

const unreadButtons = (page) => page.getByRole("button", { name: /^Open unread / });
const readButtons = (page) => page.getByRole("button", { name: /^Open (?!unread )/ });

test("starts with four messages, three unread", async ({ page }) => {
  await expect(page.getByRole("list", { name: "Messages" }).getByRole("listitem")).toHaveCount(4);
  await expect(unreadButtons(page)).toHaveCount(3);
  await expect(page.getByRole("button", { name: "Open Patch review" })).toBeVisible();
});

test("opening a message shows it and marks only it as read", async ({ page }) => {
  await page.getByRole("button", { name: "Open unread Compiler notes" }).click();

  const reader = page.getByRole("article", { name: "Message" });
  await expect(reader.getByRole("heading", { name: "Compiler notes" })).toBeVisible();
  await expect(reader).toContainText("From Grace");
  await expect(reader).toContainText("Attached are the notes from yesterday's session.");

  await expect(page.getByRole("heading", { name: "Inbox (2)" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Open Compiler notes" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Open unread Lunch on Friday?" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Open unread Launch checklist" })).toBeVisible();
  await expect(unreadButtons(page)).toHaveCount(2);
});

test("opening an already read message leaves the count unchanged", async ({ page }) => {
  await page.getByRole("button", { name: "Open Patch review" }).click();
  await expect(page.getByRole("article", { name: "Message" })).toContainText("From Linus");
  await expect(page.getByRole("heading", { name: "Inbox (3)" })).toBeVisible();
  await expect(unreadButtons(page)).toHaveCount(3);
});

test("Mark all read clears the count and unread markers", async ({ page }) => {
  await page.getByRole("button", { name: "Mark all read" }).click();
  await expect(page.getByRole("heading", { name: "Inbox (0)" })).toBeVisible();
  await expect(unreadButtons(page)).toHaveCount(0);
  await expect(readButtons(page)).toHaveCount(4);
});

test("Unread only hides read messages", async ({ page }) => {
  await page.getByLabel("Unread only").check();
  const items = page.getByRole("list", { name: "Messages" }).getByRole("listitem");
  await expect(items).toHaveCount(3);
  await expect(page.getByRole("button", { name: "Open Patch review" })).toHaveCount(0);

  await page.getByRole("button", { name: "Open unread Lunch on Friday?" }).click();
  await expect(items).toHaveCount(2);
  await expect(page.getByRole("button", { name: "Open Lunch on Friday?" })).toHaveCount(0);

  await page.getByLabel("Unread only").uncheck();
  await expect(items).toHaveCount(4);
});

test("read state persists across a reload", async ({ page }) => {
  await page.getByRole("button", { name: "Open unread Launch checklist" }).click();
  await expect(page.getByRole("heading", { name: "Inbox (2)" })).toBeVisible();

  await page.reload();
  await expect(page.getByRole("heading", { name: "Inbox (2)" })).toBeVisible();
  await expect(unreadButtons(page)).toHaveCount(2);
  await expect(page.getByRole("button", { name: "Open Launch checklist" })).toBeVisible();
});

test("Mark all read persists across a reload", async ({ page }) => {
  await page.getByRole("button", { name: "Mark all read" }).click();
  await expect(page.getByRole("heading", { name: "Inbox (0)" })).toBeVisible();

  await page.reload();
  await expect(page.getByRole("heading", { name: "Inbox (0)" })).toBeVisible();
  await expect(unreadButtons(page)).toHaveCount(0);
});
