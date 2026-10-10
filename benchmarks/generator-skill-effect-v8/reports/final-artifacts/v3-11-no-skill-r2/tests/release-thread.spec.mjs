import { expect, test } from "@playwright/test";

test.beforeEach(async ({ request }) => {
  await request.post("/api/reset");
});

test("shows seeded unread release thread for Ada", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByRole("heading", { name: "Release thread (2 new)" })).toBeVisible();
  await expect(page.getByText("2 new messages")).toBeVisible();

  const messages = page.getByRole("list", { name: "Messages" }).locator(".message");
  await expect(messages).toHaveCount(4);
  await expect(messages.nth(0)).toContainText("Grace: Did the nightly build pass?");
  await expect(messages.nth(1)).toContainText("Ada: Yes, all green since 02:00.");
  await expect(messages.nth(2)).toContainText("Linus: Then let's cut the release this afternoon.");
  await expect(messages.nth(3)).toContainText("Grace: I can prepare the notes.");
});

test("marks unread messages as read and persists after reload", async ({ page }) => {
  await page.goto("/");

  await page.getByRole("button", { name: "Mark as read" }).click();

  await expect(page.getByRole("heading", { name: "Release thread" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Release thread (2 new)" })).toHaveCount(0);
  await expect(page.getByText("2 new messages")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Mark as read" })).toBeHidden();

  await page.reload();

  await expect(page.getByRole("heading", { name: "Release thread" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Release thread (2 new)" })).toHaveCount(0);
  await expect(page.getByText("2 new messages")).toHaveCount(0);
});

test("sends quoted replies and cancels reply without sending", async ({ page }) => {
  await page.goto("/");

  await page.getByRole("button", { name: "Reply to message 3" }).click();
  await expect(page.locator("#th-quote")).toContainText("Replying to Linus: Then let's cut the release this afternoon.");

  await page.getByLabel("Your message").fill("I'll start the release checklist.");
  await page.getByRole("button", { name: "Send" }).click();

  const messages = page.getByRole("list", { name: "Messages" }).locator(".message");
  await expect(messages).toHaveCount(5);
  await expect(messages.last()).toContainText("Linus: Then let's cut the release this afternoon.");
  await expect(messages.last()).toContainText("Ada: I'll start the release checklist.");
  await expect(page.locator("#th-quote")).toBeHidden();

  await page.reload();

  await expect(page.getByRole("list", { name: "Messages" }).locator(".message")).toHaveCount(5);
  await expect(page.getByRole("list", { name: "Messages" }).locator(".message").last()).toContainText("Linus: Then let's cut the release this afternoon.");
  await expect(page.getByRole("list", { name: "Messages" }).locator(".message").last()).toContainText("Ada: I'll start the release checklist.");

  await page.getByRole("button", { name: "Reply to message 4" }).click();
  await expect(page.locator("#th-quote")).toContainText("Replying to Grace: I can prepare the notes.");
  await page.getByRole("button", { name: "Cancel reply" }).click();
  await expect(page.locator("#th-quote")).toBeHidden();
  await expect(page.getByRole("list", { name: "Messages" }).locator(".message")).toHaveCount(5);

  await page.reload();

  await expect(page.getByRole("list", { name: "Messages" }).locator(".message")).toHaveCount(5);
  await expect(page.getByRole("list", { name: "Messages" }).locator(".message").nth(3)).toContainText("Grace: I can prepare the notes.");
});

test("edits Ada's message in place and persists after reload", async ({ page }) => {
  await page.goto("/");

  await page.getByRole("button", { name: "Edit message 2" }).click();
  await page.getByLabel("Edit text of message 2").fill("Yes, all green since 02:30.");
  await page.getByRole("button", { name: "Save message 2" }).click();

  const adaMessage = page.getByRole("list", { name: "Messages" }).locator(".message").nth(1);
  await expect(adaMessage).toContainText("Ada: Yes, all green since 02:30. (edited)");
  await expect(page.getByText("Yes, all green since 02:00.")).toHaveCount(0);

  await page.reload();

  const reloadedAdaMessage = page.getByRole("list", { name: "Messages" }).locator(".message").nth(1);
  await expect(reloadedAdaMessage).toContainText("Ada: Yes, all green since 02:30. (edited)");
  await expect(page.getByText("Yes, all green since 02:00.")).toHaveCount(0);
});
