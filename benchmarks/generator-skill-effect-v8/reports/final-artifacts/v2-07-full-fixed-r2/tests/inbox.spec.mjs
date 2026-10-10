import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page, request }) => {
  await request.post("/api/reset");
  await page.goto("/");
});

test("shows the seeded inbox unread count and unread markers", async ({ page }) => {
  const messages = page.getByRole("list", { name: "Messages", exact: true });

  await expect(page.getByRole("heading", { name: /^Inbox \(3\)$/ })).toBeVisible();
  await expect(messages.getByRole("listitem")).toHaveCount(4);
  await expect(messages.getByRole("button", { name: "Open unread Lunch on Friday?", exact: true })).toBeVisible();
  await expect(messages.getByRole("button", { name: "Open unread Compiler notes", exact: true })).toBeVisible();
  await expect(messages.getByRole("button", { name: "Open Patch review", exact: true })).toBeVisible();
  await expect(messages.getByRole("button", { name: "Open unread Launch checklist", exact: true })).toBeVisible();
});

test("opens one unread message and persists only that message as read", async ({ page }) => {
  const messages = page.getByRole("list", { name: "Messages", exact: true });
  const readRequest = page.waitForResponse((response) =>
    response.url().endsWith("/api/messages/2/read") &&
    response.request().method() === "POST"
  );

  await messages.getByRole("button", { name: "Open unread Compiler notes", exact: true }).click();
  const response = await readRequest;
  const reader = page.getByRole("article", { name: "Message", exact: true });

  expect(response.status()).toBe(200);
  await expect(page.getByRole("heading", { name: /^Inbox \(2\)$/ })).toBeVisible();
  await expect(reader).toContainText("Compiler notes");
  await expect(reader).toContainText("From Grace");
  await expect(reader).toContainText("Attached are the notes from yesterday's session.");
  await expect(messages.getByRole("button", { name: "Open unread Lunch on Friday?", exact: true })).toBeVisible();
  await expect(messages.getByRole("button", { name: "Open Compiler notes", exact: true })).toBeVisible();
  await expect(messages.getByRole("button", { name: "Open Patch review", exact: true })).toBeVisible();
  await expect(messages.getByRole("button", { name: "Open unread Launch checklist", exact: true })).toBeVisible();

  await page.reload();

  await expect(page.getByRole("heading", { name: /^Inbox \(2\)$/ })).toBeVisible();
  await expect(messages.getByRole("button", { name: "Open unread Lunch on Friday?", exact: true })).toBeVisible();
  await expect(messages.getByRole("button", { name: "Open Compiler notes", exact: true })).toBeVisible();
  await expect(messages.getByRole("button", { name: "Open Patch review", exact: true })).toBeVisible();
  await expect(messages.getByRole("button", { name: "Open unread Launch checklist", exact: true })).toBeVisible();
});

test("filters the inbox to unread messages only", async ({ page }) => {
  const messages = page.getByRole("list", { name: "Messages", exact: true });

  await page.getByRole("checkbox", { name: "Unread only", exact: true }).check();

  await expect(page.getByRole("heading", { name: /^Inbox \(3\)$/ })).toBeVisible();
  await expect(messages.getByRole("listitem")).toHaveCount(3);
  await expect(messages.getByRole("button", { name: "Open unread Lunch on Friday?", exact: true })).toBeVisible();
  await expect(messages.getByRole("button", { name: "Open unread Compiler notes", exact: true })).toBeVisible();
  await expect(messages.getByRole("button", { name: "Open Patch review", exact: true })).toHaveCount(0);
  await expect(messages.getByRole("button", { name: "Open unread Launch checklist", exact: true })).toBeVisible();
});

test("marks every message read and clears unread-only results", async ({ page }) => {
  const messages = page.getByRole("list", { name: "Messages", exact: true });
  const readAllRequest = page.waitForResponse((response) =>
    response.url().endsWith("/api/messages/read-all") &&
    response.request().method() === "POST"
  );

  await expect(messages.getByRole("listitem")).toHaveCount(4);
  await page.getByRole("button", { name: "Mark all read", exact: true }).click();
  const response = await readAllRequest;

  expect(response.status()).toBe(200);
  await expect(page.getByRole("heading", { name: /^Inbox \(0\)$/ })).toBeVisible();
  await expect(messages.getByRole("button", { name: /^Open unread / })).toHaveCount(0);
  await expect(messages.getByRole("button", { name: "Open Lunch on Friday?", exact: true })).toBeVisible();
  await expect(messages.getByRole("button", { name: "Open Compiler notes", exact: true })).toBeVisible();
  await expect(messages.getByRole("button", { name: "Open Patch review", exact: true })).toBeVisible();
  await expect(messages.getByRole("button", { name: "Open Launch checklist", exact: true })).toBeVisible();

  await page.getByRole("checkbox", { name: "Unread only", exact: true }).check();

  await expect(messages.getByRole("listitem")).toHaveCount(0);
});
