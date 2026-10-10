import { expect, test } from "@playwright/test";

const heading = (page) => page.getByRole("heading", { level: 1 });
const row = (page, subject) =>
  page.getByRole("listitem").filter({ has: page.getByRole("button", { name: new RegExp(subject) }) });

test.beforeEach(async ({ page, request }) => {
  const res = await request.post("/api/reset");
  expect(res.ok()).toBeTruthy();
  await page.goto("/");
  await expect(heading(page)).toHaveText("Inbox (3)");
});

test("lists the four seeded messages with unread markers", async ({ page }) => {
  await expect(page.getByRole("listitem")).toHaveCount(4);
  await expect(page.locator("li.unread")).toHaveCount(3);
  await expect(row(page, "Patch review")).toHaveClass(/\bread\b/);
  await expect(row(page, "Lunch on Friday\\?")).toHaveClass(/\bunread\b/);
});

test("opening a message shows it and marks only it as read", async ({ page }) => {
  await page.getByRole("button", { name: "Open unread Compiler notes" }).click();

  const reader = page.getByRole("article", { name: "Message" });
  await expect(reader.getByRole("heading", { name: "Compiler notes" })).toBeVisible();
  await expect(reader).toContainText("From Grace");
  await expect(reader).toContainText("Attached are the notes from yesterday's session.");

  await expect(heading(page)).toHaveText("Inbox (2)");
  await expect(page.getByRole("button", { name: "Open Compiler notes" })).toBeVisible();
  await expect(row(page, "Compiler notes")).toHaveClass(/\bread\b/);
  await expect(page.getByRole("button", { name: "Open unread Lunch on Friday?" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Open unread Launch checklist" })).toBeVisible();
  await expect(page.locator("li.unread")).toHaveCount(2);
});

test("opening an already read message keeps the count", async ({ page }) => {
  await page.getByRole("button", { name: "Open Patch review" }).click();
  await expect(page.getByRole("article", { name: "Message" })).toContainText("From Linus");
  await expect(heading(page)).toHaveText("Inbox (3)");
});

test("Mark all read clears the count and the unread markers", async ({ page }) => {
  await page.getByRole("button", { name: "Mark all read" }).click();
  await expect(heading(page)).toHaveText("Inbox (0)");
  await expect(page.locator("li.unread")).toHaveCount(0);
  await expect(page.getByRole("button", { name: /^Open unread/ })).toHaveCount(0);
  await expect(page.getByRole("listitem")).toHaveCount(4);
});

test("Unread only hides read messages", async ({ page }) => {
  await page.getByLabel("Unread only").check();
  await expect(page.getByRole("listitem")).toHaveCount(3);
  await expect(page.getByRole("button", { name: "Open Patch review" })).toHaveCount(0);

  await page.getByRole("button", { name: "Open unread Lunch on Friday?" }).click();
  await expect(page.getByRole("listitem")).toHaveCount(2);
  await expect(page.getByRole("button", { name: /Lunch on Friday/ })).toHaveCount(0);

  await page.getByLabel("Unread only").uncheck();
  await expect(page.getByRole("listitem")).toHaveCount(4);
});

test("read state persists across a reload", async ({ page }) => {
  await page.getByRole("button", { name: "Open unread Launch checklist" }).click();
  await expect(heading(page)).toHaveText("Inbox (2)");

  await page.reload();
  await expect(heading(page)).toHaveText("Inbox (2)");
  await expect(page.locator("li.unread")).toHaveCount(2);
  await expect(page.getByRole("button", { name: "Open Launch checklist" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Open unread Lunch on Friday?" })).toBeVisible();
});

test("Mark all read persists across a reload", async ({ page }) => {
  await page.getByRole("button", { name: "Mark all read" }).click();
  await expect(heading(page)).toHaveText("Inbox (0)");

  await page.reload();
  await expect(heading(page)).toHaveText("Inbox (0)");
  await expect(page.locator("li.unread")).toHaveCount(0);
});
