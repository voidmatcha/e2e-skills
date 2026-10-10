import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page, request }) => {
  const response = await request.post("/api/reset");
  if (!response.ok()) {
    throw new Error(`Failed to reset inbox state: ${response.status()}`);
  }

  await page.goto("/");
});

test("shows the seeded unread count and message markers", async ({ page }) => {
  await expect(page.getByRole("heading", { name: "Inbox (3)" })).toBeVisible();
  await expect(page.getByRole("list", { name: "Messages" }).getByRole("button", { name: /^Open unread / })).toHaveCount(3);
  await expect(page.getByRole("button", { name: "Open Patch review" })).toBeVisible();
});

test("opens one message, marks only that message read, and keeps state after reload", async ({ page }) => {
  const messages = page.getByRole("list", { name: "Messages" });
  const readRequest = page.waitForRequest((request) =>
    request.method() === "POST" && request.url().endsWith("/api/messages/1/read")
  );

  await page.getByRole("button", { name: "Open unread Lunch on Friday?" }).click();
  await readRequest;

  const reader = page.getByRole("article", { name: "Message" });

  await expect(reader.getByRole("heading", { name: "Lunch on Friday?" })).toBeVisible();
  await expect(reader.getByText("From Ada")).toBeVisible();
  await expect(reader.getByText("Shall we try the new place by the river?")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Inbox (2)" })).toBeVisible();
  await expect(messages.getByRole("button", { name: "Open Lunch on Friday?" })).toBeVisible();
  await expect(messages.getByRole("button", { name: /^Open unread / })).toHaveCount(2);
  await expect(messages.getByRole("button", { name: "Open unread Compiler notes" })).toBeVisible();
  await expect(messages.getByRole("button", { name: "Open Patch review" })).toBeVisible();
  await expect(messages.getByRole("button", { name: "Open unread Launch checklist" })).toBeVisible();

  await page.reload();

  await expect(page.getByRole("heading", { name: "Inbox (2)" })).toBeVisible();
  await expect(messages.getByRole("button", { name: "Open Lunch on Friday?" })).toBeVisible();
  await expect(messages.getByRole("button", { name: /^Open unread / })).toHaveCount(2);
});

test("marks every message read", async ({ page }) => {
  const messages = page.getByRole("list", { name: "Messages" });
  const unreadMessages = messages.getByRole("button", { name: /^Open unread / });
  const readAllRequest = page.waitForRequest((request) =>
    request.method() === "POST" && request.url().endsWith("/api/messages/read-all")
  );

  await expect(unreadMessages).toHaveCount(3);
  await page.getByRole("button", { name: "Mark all read" }).click();
  await readAllRequest;

  await expect(page.getByRole("heading", { name: "Inbox (0)" })).toBeVisible();
  await expect(unreadMessages).toHaveCount(0);
});

test("filters the list to unread messages only", async ({ page }) => {
  const messages = page.getByRole("list", { name: "Messages" });
  const readMessage = page.getByRole("button", { name: "Open Patch review" });

  await expect(readMessage).toBeVisible();
  await page.getByRole("checkbox", { name: "Unread only" }).check();

  await expect(messages.getByRole("button", { name: /^Open unread / })).toHaveCount(3);
  await expect(readMessage).toBeHidden();
});
