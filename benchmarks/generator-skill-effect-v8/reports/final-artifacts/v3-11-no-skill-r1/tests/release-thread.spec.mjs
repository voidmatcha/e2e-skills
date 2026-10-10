import { expect, test } from "@playwright/test";

test.beforeEach(async ({ request }) => {
  await request.post("/api/reset");
});

test("shows seeded unread messages with the new-message divider", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByRole("heading", { name: "Release thread (2 new)" })).toBeVisible();

  const items = page.locator("#th-messages > li");
  await expect(items).toHaveCount(5);
  await expect(items.nth(0)).toContainText("Grace: Did the nightly build pass?");
  await expect(items.nth(1)).toContainText("Ada: Yes, all green since 02:00.");
  await expect(items.nth(2)).toHaveText("2 new messages");
  await expect(items.nth(3)).toContainText("Linus: Then let's cut the release this afternoon.");
  await expect(items.nth(4)).toContainText("Grace: I can prepare the notes.");
});

test("marks unread messages as read on the server and keeps them read after reload", async ({
  page,
  request,
}) => {
  await page.goto("/");

  await page.getByRole("button", { name: "Mark as read" }).click();

  await expect(page.getByRole("heading", { name: "Release thread", exact: true })).toBeVisible();
  await expect(page.locator("#th-messages > .divider")).toHaveCount(0);
  await expect(page.getByText("2 new messages")).toHaveCount(0);

  const thread = await (await request.get("/api/thread")).json();
  expect(thread.lastReadId).toBe(4);

  await page.reload();
  await expect(page.getByRole("heading", { name: "Release thread", exact: true })).toBeVisible();
  await expect(page.locator("#th-messages > .divider")).toHaveCount(0);
  await expect(page.getByText("2 new messages")).toHaveCount(0);
});

test("sends a quoted reply, persists it after reload, and can cancel a reply without sending", async ({
  page,
}) => {
  await page.goto("/");

  await page.getByRole("button", { name: "Reply to message 3" }).click();
  await expect(page.locator("#th-quote")).toBeVisible();
  await expect(page.locator("#th-quote-text")).toHaveText(
    "Linus: Then let's cut the release this afternoon.",
  );

  await page.getByLabel("Your message").fill("Agreed, I will watch deploy.");
  await page.getByRole("button", { name: "Send" }).click();

  const sentMessage = page.locator("#th-messages > li").last();
  await expect(sentMessage.locator("blockquote")).toHaveText(
    "Linus: Then let's cut the release this afternoon.",
  );
  await expect(sentMessage).toContainText("Ada: Agreed, I will watch deploy.");

  await page.reload();
  const persistedMessage = page.locator("#th-messages > li").last();
  await expect(persistedMessage.locator("blockquote")).toHaveText(
    "Linus: Then let's cut the release this afternoon.",
  );
  await expect(persistedMessage).toContainText("Ada: Agreed, I will watch deploy.");

  await page.getByRole("button", { name: "Reply to message 4" }).click();
  await expect(page.locator("#th-quote-text")).toHaveText("Grace: I can prepare the notes.");

  await page.getByRole("button", { name: "Cancel reply" }).click();

  await expect(page.locator("#th-quote")).toBeHidden();
  await expect(page.locator("#th-messages > li")).toHaveCount(5);
});

test("edits Ada's message in place and keeps the edited marker after reload", async ({ page }) => {
  await page.goto("/");

  await page.getByRole("button", { name: "Edit message 2" }).click();
  await page.getByLabel("Edit text of message 2").fill("Yes, green since 02:00 and ready.");
  await page.getByRole("button", { name: "Save message 2" }).click();

  const adaMessage = page.locator("#th-messages > li").filter({ hasText: "Ada:" }).first();
  await expect(adaMessage).toContainText("Ada: Yes, green since 02:00 and ready. (edited)");

  await page.reload();
  await expect(page.locator("#th-messages > li").filter({ hasText: "Ada:" }).first()).toContainText(
    "Ada: Yes, green since 02:00 and ready. (edited)",
  );
});
