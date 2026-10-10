import { expect, test } from "@playwright/test";

const heading = (page) => page.getByRole("heading", { name: /Release thread/ });
const messages = (page) => page.getByRole("list", { name: "Messages" });
const divider = (page) => messages(page).getByText(/^\d+ new messages?$/);
const message = (page, text) => messages(page).getByRole("listitem").filter({ hasText: text });

test.beforeEach(async ({ page, request }) => {
  await request.post("/api/reset");
  await page.goto("/");
  await expect(heading(page)).toHaveText("Release thread (2 new)");
});

test("shows the seeded thread with an unread divider above the first unread message", async ({ page }) => {
  await expect(messages(page).locator("li.message")).toHaveCount(4);
  await expect(divider(page)).toHaveText("2 new messages");
  const items = messages(page).getByRole("listitem");
  await expect(items.nth(2)).toHaveText("2 new messages");
  await expect(items.nth(3)).toContainText("Then let's cut the release this afternoon.");
});

test("Mark as read clears the divider and count, and persists after reload", async ({ page }) => {
  await page.getByRole("button", { name: "Mark as read" }).click();
  await expect(heading(page)).toHaveText("Release thread");
  await expect(divider(page)).toHaveCount(0);

  await page.reload();
  await expect(heading(page)).toHaveText("Release thread");
  await expect(messages(page).locator("li.message")).toHaveCount(4);
  await expect(divider(page)).toHaveCount(0);
});

test("Reply shows the quote above the composer and the sent message carries it", async ({ page }) => {
  await page.getByRole("button", { name: "Reply to message 4" }).click();
  const quote = page.locator("#th-quote");
  await expect(quote).toContainText("Grace: I can prepare the notes.");

  const composer = page.getByRole("textbox", { name: "Your message" });
  const quoteBox = await quote.boundingBox();
  const composerBox = await composer.boundingBox();
  expect(quoteBox.y + quoteBox.height).toBeLessThanOrEqual(composerBox.y);

  await composer.fill("Thanks, please do.");
  await page.getByRole("button", { name: "Send" }).click();

  const sent = message(page, "Thanks, please do.");
  await expect(sent.locator("blockquote")).toHaveText("Grace: I can prepare the notes.");
  await expect(quote).toBeHidden();

  await page.reload();
  await expect(message(page, "Thanks, please do.").locator("blockquote")).toHaveText("Grace: I can prepare the notes.");
});

test("Cancel reply removes the quote without sending", async ({ page }) => {
  await page.getByRole("button", { name: "Reply to message 3" }).click();
  await expect(page.locator("#th-quote")).toBeVisible();
  await page.getByRole("button", { name: "Cancel reply" }).click();
  await expect(page.locator("#th-quote")).toBeHidden();
  await expect(messages(page).locator("li.message")).toHaveCount(4);

  const thread = await (await page.request.get("/api/thread")).json();
  expect(thread.messages).toHaveLength(4);

  // A message sent afterwards carries no quote.
  await page.getByRole("textbox", { name: "Your message" }).fill("Plain message");
  await page.getByRole("button", { name: "Send" }).click();
  await expect(message(page, "Plain message")).toBeVisible();
  await expect(message(page, "Plain message").locator("blockquote")).toHaveCount(0);
});

test("Edit changes Ada's message in place, marks it (edited) and persists", async ({ page }) => {
  await page.getByRole("button", { name: "Edit message 2" }).click();
  await page.getByRole("textbox", { name: "Edit text of message 2" }).fill("Green since 02:00, confirmed.");
  await page.getByRole("button", { name: "Save message 2" }).click();

  const edited = message(page, "Green since 02:00, confirmed.");
  await expect(edited).toContainText("Green since 02:00, confirmed. (edited)");
  await expect(messages(page).locator("li.message")).toHaveCount(4);
  await expect(messages(page).locator("li.message").nth(1)).toContainText("(edited)");

  await page.reload();
  await expect(message(page, "Green since 02:00, confirmed.")).toContainText("(edited)");
  await expect(message(page, "Yes, all green")).toHaveCount(0);
});

test("only Ada's own messages offer Edit", async ({ page }) => {
  await expect(page.getByRole("button", { name: /^Edit message/ })).toHaveCount(1);
  await expect(page.getByRole("button", { name: "Edit message 2" })).toBeVisible();
});
