import { expect, test } from "@playwright/test";

const messages = (page) => page.getByRole("list", { name: "Messages" });
const message = (page, text) => messages(page).getByRole("listitem").filter({ hasText: text });

test.beforeEach(async ({ page, request }) => {
  const res = await request.post("/api/reset");
  expect(res.ok()).toBeTruthy();
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Release thread (2 new)" })).toBeVisible();
});

test("shows four messages, the unread count and a divider above the first unread", async ({ page }) => {
  await expect(messages(page).getByRole("listitem")).toHaveCount(5);
  await expect(message(page, "2 new messages")).toHaveCount(1);
  const items = messages(page).getByRole("listitem");
  await expect(items.nth(0)).toContainText("Did the nightly build pass?");
  await expect(items.nth(1)).toContainText("Yes, all green since 02:00.");
  await expect(items.nth(2)).toHaveText("2 new messages");
  await expect(items.nth(3)).toContainText("Then let's cut the release this afternoon.");
  await expect(items.nth(4)).toContainText("I can prepare the notes.");
});

test("Mark as read removes the divider and count, and persists on reload", async ({ page }) => {
  await page.getByRole("button", { name: "Mark as read" }).click();
  await expect(page.getByRole("heading", { name: "Release thread", exact: true })).toBeVisible();
  await expect(page.getByText("2 new messages")).toHaveCount(0);
  await page.reload();
  await expect(page.getByRole("heading", { name: "Release thread", exact: true })).toBeVisible();
  await expect(messages(page).getByRole("listitem")).toHaveCount(4);
  await expect(page.getByText("2 new messages")).toHaveCount(0);
});

test("Reply shows the quote and the sent message carries it across a reload", async ({ page }) => {
  await page.getByRole("button", { name: "Reply to message 3" }).click();
  await expect(page.getByText("Replying to")).toBeVisible();
  await expect(page.locator("#th-quote-text")).toHaveText("Linus: Then let's cut the release this afternoon.");
  await page.getByRole("textbox", { name: "Your message" }).fill("Agreed, 3pm?");
  await page.getByRole("button", { name: "Send" }).click();
  await expect(page.getByText("Replying to")).toBeHidden();
  const sent = message(page, "Agreed, 3pm?");
  await expect(sent.locator("blockquote")).toHaveText("Linus: Then let's cut the release this afternoon.");

  await page.reload();
  const reloaded = message(page, "Agreed, 3pm?");
  await expect(reloaded).toHaveCount(1);
  await expect(reloaded.locator("blockquote")).toHaveText("Linus: Then let's cut the release this afternoon.");
});

test("Cancel reply removes the quote without sending", async ({ page }) => {
  await page.getByRole("button", { name: "Reply to message 1" }).click();
  await expect(page.locator("#th-quote-text")).toHaveText("Grace: Did the nightly build pass?");
  await page.getByRole("button", { name: "Cancel reply" }).click();
  await expect(page.getByText("Replying to")).toBeHidden();
  await expect(messages(page).getByRole("listitem")).toHaveCount(5);

  await page.getByRole("textbox", { name: "Your message" }).fill("Plain message");
  await page.getByRole("button", { name: "Send" }).click();
  await expect(message(page, "Plain message")).toHaveCount(1);
  await expect(message(page, "Plain message").locator("blockquote")).toHaveCount(0);
});

test("a sent message is stored on the server", async ({ page }) => {
  await page.getByRole("textbox", { name: "Your message" }).fill("Shipping now");
  await page.getByRole("button", { name: "Send" }).click();
  await expect(message(page, "Shipping now")).toHaveCount(1);
  await page.reload();
  await expect(message(page, "Shipping now")).toHaveCount(1);
  await expect(messages(page).getByRole("listitem")).toHaveCount(5);
});

test("Edit changes Ada's message in place, marks it (edited) and persists", async ({ page }) => {
  await expect(page.getByRole("button", { name: "Edit message 1" })).toHaveCount(0);
  await page.getByRole("button", { name: "Edit message 2" }).click();
  await page.getByRole("textbox", { name: "Edit text of message 2" }).fill("Yes, green since 01:30.");
  await page.getByRole("button", { name: "Save message 2" }).click();

  const edited = message(page, "Yes, green since 01:30.");
  await expect(edited).toContainText("Yes, green since 01:30. (edited)");
  await expect(messages(page).getByRole("listitem")).toHaveCount(5);

  await page.reload();
  await expect(message(page, "Yes, green since 01:30.")).toContainText("(edited)");
  await expect(page.getByText("Yes, all green since 02:00.")).toHaveCount(0);
});
