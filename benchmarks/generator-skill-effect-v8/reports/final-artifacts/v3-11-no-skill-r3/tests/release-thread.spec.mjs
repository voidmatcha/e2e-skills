import { expect, test } from "@playwright/test";

test.beforeEach(async ({ request }) => {
  await request.post("/api/reset");
});

test("shows seeded unread messages and persists mark as read", async ({ page, request }) => {
  await page.goto("/");

  await expect(page.getByRole("heading", { name: "Release thread (2 new)" })).toBeVisible();
  await expect(page.getByText("2 new messages")).toBeVisible();

  const items = page.locator("#th-messages > li");
  await expect(items).toHaveCount(5);
  await expect(items.nth(0)).toContainText("Grace: Did the nightly build pass?");
  await expect(items.nth(1)).toContainText("Ada: Yes, all green since 02:00.");
  await expect(items.nth(2)).toHaveText("2 new messages");
  await expect(items.nth(3)).toContainText("Linus: Then let's cut the release this afternoon.");
  await expect(items.nth(4)).toContainText("Grace: I can prepare the notes.");

  await page.getByRole("button", { name: "Mark as read" }).click();
  await expect(page.getByRole("heading", { name: "Release thread", exact: true })).toBeVisible();
  await expect(page.getByText("new messages")).toBeHidden();

  const thread = await (await request.get("/api/thread")).json();
  expect(thread.lastReadId).toBe(4);

  await page.reload();
  await expect(page.getByRole("heading", { name: "Release thread", exact: true })).toBeVisible();
  await expect(page.getByText("new messages")).toBeHidden();
});

test("sends quoted replies and cancels replies without sending", async ({ page }) => {
  await page.goto("/");

  await page.getByRole("button", { name: "Reply to message 4" }).click();
  await expect(page.getByText("Replying to Grace: I can prepare the notes.")).toBeVisible();

  await page.getByLabel("Your message").fill("Thanks, please add the rollout checklist.");
  await page.getByRole("button", { name: "Send" }).click();

  const sentReply = page.locator("#th-messages > li").filter({
    hasText: "Thanks, please add the rollout checklist.",
  });
  await expect(sentReply).toContainText("Grace: I can prepare the notes.");
  await expect(sentReply).toContainText("Ada: Thanks, please add the rollout checklist.");

  await page.reload();
  await expect(page.locator("#th-messages > li").filter({
    hasText: "Thanks, please add the rollout checklist.",
  })).toContainText("Grace: I can prepare the notes.");

  await page.getByRole("button", { name: "Reply to message 3" }).click();
  await page.getByLabel("Your message").fill("This should stay in the composer.");
  await page.getByRole("button", { name: "Cancel reply" }).click();

  await expect(page.getByText("Replying to")).toBeHidden();
  await expect(page.locator("#th-messages > li")).toHaveCount(5);
  await expect(page.getByText("This should stay in the composer.")).toBeHidden();
});

test("edits Ada's message in place and persists the edited marker", async ({ page }) => {
  await page.goto("/");

  await page.getByRole("button", { name: "Edit message 2" }).click();
  await page.getByLabel("Edit text of message 2").fill("Yes, all green since the 02:00 rebuild.");
  await page.getByRole("button", { name: "Save message 2" }).click();

  const editedMessage = page.locator("#th-messages > li").filter({
    hasText: "Yes, all green since the 02:00 rebuild. (edited)",
  });
  await expect(editedMessage).toContainText("Ada: Yes, all green since the 02:00 rebuild. (edited)");

  await page.reload();
  await expect(page.locator("#th-messages > li").filter({
    hasText: "Yes, all green since the 02:00 rebuild. (edited)",
  })).toContainText("Ada: Yes, all green since the 02:00 rebuild. (edited)");
});
