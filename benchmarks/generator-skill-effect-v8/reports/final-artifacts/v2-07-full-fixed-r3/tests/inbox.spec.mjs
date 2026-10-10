import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  await page.request.post("/api/reset");
  await page.goto("/");
  await expect(page.getByRole("heading", { name: /^Inbox \(3\)$/ })).toBeVisible();
});

test("opens an unread message, stores it as read, and filters unread messages", async ({ page }) => {
  const messages = page.getByRole("list", { name: "Messages", exact: true });

  await expect(messages.getByRole("button", { name: /^Open unread / })).toHaveCount(3);
  await expect(messages.getByRole("button", { name: "Open Patch review", exact: true })).toBeVisible();

  const readRequest = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      response.url().endsWith("/api/messages/1/read") &&
      response.status() === 200,
  );
  await messages.getByRole("button", { name: "Open unread Lunch on Friday?", exact: true }).click();
  await readRequest;

  await expect(page.getByRole("heading", { name: /^Inbox \(2\)$/ })).toBeVisible();
  const reader = page.getByRole("article", { name: "Message", exact: true });
  await expect(reader.getByRole("heading", { name: "Lunch on Friday?", exact: true })).toBeVisible();
  await expect(reader).toContainText("From Ada");
  await expect(reader).toContainText("Shall we try the new place by the river?");
  await expect(messages.getByRole("button", { name: "Open Lunch on Friday?", exact: true })).toBeVisible();
  await expect(messages.getByRole("button", { name: /^Open unread / })).toHaveCount(2);

  await page.reload();

  await expect(page.getByRole("heading", { name: /^Inbox \(2\)$/ })).toBeVisible();
  await expect(messages.getByRole("button", { name: "Open Lunch on Friday?", exact: true })).toBeVisible();
  await expect(messages.getByRole("button", { name: /^Open unread / })).toHaveCount(2);

  await page.getByRole("checkbox", { name: "Unread only", exact: true }).check();

  await expect(messages.getByRole("listitem")).toHaveCount(2);
  await expect(messages.getByRole("button", { name: "Open unread Compiler notes", exact: true })).toBeVisible();
  await expect(messages.getByRole("button", { name: "Open unread Launch checklist", exact: true })).toBeVisible();
});

test("marks every message read and clears unread-only results", async ({ page }) => {
  const messages = page.getByRole("list", { name: "Messages", exact: true });
  await expect(messages.getByRole("listitem")).toHaveCount(4);

  const markAllRequest = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      response.url().endsWith("/api/messages/read-all") &&
      response.status() === 200,
  );

  await page.getByRole("button", { name: "Mark all read", exact: true }).click();
  await markAllRequest;
  await page.reload();

  await expect(page.getByRole("heading", { name: /^Inbox \(0\)$/ })).toBeVisible();
  await expect(messages.getByRole("button", { name: "Open Lunch on Friday?", exact: true })).toBeVisible();
  await expect(messages.getByRole("button", { name: "Open Compiler notes", exact: true })).toBeVisible();
  await expect(messages.getByRole("button", { name: "Open Patch review", exact: true })).toBeVisible();
  await expect(messages.getByRole("button", { name: "Open Launch checklist", exact: true })).toBeVisible();

  await page.getByRole("checkbox", { name: "Unread only", exact: true }).check();

  await expect(messages.getByRole("listitem")).toHaveCount(0);
});
