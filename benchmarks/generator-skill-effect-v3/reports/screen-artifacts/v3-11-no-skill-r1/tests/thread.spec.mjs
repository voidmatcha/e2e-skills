import { expect, test } from "@playwright/test";

const message = (page, text) => page.getByRole("listitem").filter({ hasText: text });
const heading = (page) => page.getByRole("heading", { name: /Release thread/ });
const divider = (page) => page.getByText(/\d+ new messages?$/);

test.beforeEach(async ({ page, request }) => {
  await request.post("/api/reset");
  await page.goto("/");
  await expect(page.getByRole("list", { name: "Messages" }).getByRole("listitem")).toHaveCount(5);
});

test("shows unread count and divider above the first unread message", async ({ page }) => {
  await expect(heading(page)).toHaveText("Release thread (2 new)");
  await expect(divider(page)).toHaveText("2 new messages");
  const items = page.getByRole("list", { name: "Messages" }).getByRole("listitem");
  await expect(items.nth(2)).toHaveText("2 new messages");
  await expect(items.nth(3)).toContainText("Then let's cut the release this afternoon.");
});

test("mark as read clears divider and count, persisted on the server", async ({ page }) => {
  await page.getByRole("button", { name: "Mark as read" }).click();
  await expect(heading(page)).toHaveText("Release thread");
  await expect(divider(page)).toHaveCount(0);
  await page.reload();
  await expect(message(page, "I can prepare the notes.")).toBeVisible();
  await expect(heading(page)).toHaveText("Release thread");
  await expect(divider(page)).toHaveCount(0);
});

test("reply shows the quote above the composer and the sent message carries it", async ({ page }) => {
  await page.getByRole("button", { name: "Reply to message 4" }).click();
  const quote = page.locator("#th-quote");
  await expect(quote).toContainText("Grace: I can prepare the notes.");
  const quoteBox = await quote.boundingBox();
  const composerBox = await page.getByRole("textbox", { name: "Your message" }).boundingBox();
  expect(quoteBox.y + quoteBox.height).toBeLessThanOrEqual(composerBox.y);

  await page.getByRole("textbox", { name: "Your message" }).fill("Thanks, please share them.");
  await page.getByRole("button", { name: "Send" }).click();

  const sent = message(page, "Thanks, please share them.");
  await expect(sent.locator("blockquote")).toHaveText("Grace: I can prepare the notes.");
  await expect(quote).toBeHidden();

  await page.reload();
  const reloaded = message(page, "Thanks, please share them.");
  await expect(reloaded.locator("blockquote")).toHaveText("Grace: I can prepare the notes.");
});

test("cancel reply removes the quote without sending", async ({ page }) => {
  await page.getByRole("button", { name: "Reply to message 1" }).click();
  await expect(page.locator("#th-quote")).toBeVisible();
  await page.getByRole("button", { name: "Cancel reply" }).click();
  await expect(page.locator("#th-quote")).toBeHidden();
  await expect(page.getByRole("list", { name: "Messages" }).getByRole("listitem")).toHaveCount(5);
  await expect(page.locator("blockquote")).toHaveCount(0);
  await page.reload();
  await expect(page.getByRole("list", { name: "Messages" }).getByRole("listitem")).toHaveCount(5);
});

test("sending a plain message persists it", async ({ page }) => {
  await page.getByRole("textbox", { name: "Your message" }).fill("Shipping at 15:00.");
  await page.getByRole("button", { name: "Send" }).click();
  await expect(message(page, "Shipping at 15:00.")).toBeVisible();
  await page.reload();
  await expect(message(page, "Shipping at 15:00.")).toBeVisible();
});

test("editing Ada's message updates it in place and marks it edited", async ({ page }) => {
  const items = page.getByRole("list", { name: "Messages" }).getByRole("listitem");
  await page.getByRole("button", { name: "Edit message 2" }).click();
  await page.getByRole("textbox", { name: "Edit text of message 2" }).fill("Yes, green since 01:30.");
  await page.getByRole("button", { name: "Save message 2" }).click();

  await expect(items).toHaveCount(5);
  await expect(items.nth(1)).toContainText("Yes, green since 01:30. (edited)");
  await page.reload();
  await expect(items.nth(1)).toContainText("Yes, green since 01:30. (edited)");
});

test("only Ada's own messages offer Edit", async ({ page }) => {
  await expect(page.getByRole("button", { name: /^Edit message/ })).toHaveCount(1);
  await expect(page.getByRole("button", { name: "Edit message 2" })).toBeVisible();
});
