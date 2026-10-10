import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  await page.request.post("/api/reset");
  await page.goto("/");
});

test("shows unread messages and persists marking them as read", async ({ page }) => {
  const heading = page.getByRole("heading", { name: "Release thread (2 new)", exact: true });
  const messages = page.getByRole("list", { name: "Messages", exact: true }).getByRole("listitem");

  await expect(heading).toBeVisible();
  await expect(messages).toHaveText([
    /Grace: Did the nightly build pass\?/,
    /Ada: Yes, all green since 02:00\./,
    "2 new messages",
    /Linus: Then let's cut the release this afternoon\./,
    /Grace: I can prepare the notes\./,
  ]);

  const readRequest = page.waitForRequest((request) => request.method() === "POST" && request.url().endsWith("/api/read"));
  await page.getByRole("button", { name: "Mark as read", exact: true }).click();
  await readRequest;

  await expect(page.getByRole("heading", { name: "Release thread", exact: true })).toBeVisible();
  await expect(page.getByText("2 new messages")).not.toBeVisible();

  await page.reload();
  await expect(page.getByRole("heading", { name: "Release thread", exact: true })).toBeVisible();
  await expect(page.getByText("2 new messages")).not.toBeVisible();
});

test("sends quoted replies and cancels reply mode without sending", async ({ page }) => {
  const messages = page.getByRole("list", { name: "Messages", exact: true });
  const quoteText = "Linus: Then let's cut the release this afternoon.";
  const replyText = "Release notes are ready for review.";
  const composer = page.getByRole("textbox", { name: "Your message", exact: true });

  await page.getByRole("button", { name: "Reply to message 3", exact: true }).click();
  await expect(page.getByText(`Replying to ${quoteText}`)).toBeVisible();
  await expect
    .poll(async () => {
      const quoteBox = await page.getByText(`Replying to ${quoteText}`).boundingBox();
      const composerBox = await composer.boundingBox();
      return quoteBox && composerBox ? quoteBox.y < composerBox.y : false;
    })
    .toBe(true);

  await composer.fill(replyText);
  const createRequest = page.waitForRequest((request) => request.method() === "POST" && request.url().endsWith("/api/messages"));
  await page.getByRole("button", { name: "Send", exact: true }).click();
  const request = await createRequest;
  expect(request.postDataJSON()).toEqual({ text: replyText, quote: quoteText });

  const sentMessage = messages.getByRole("listitem").filter({ hasText: replyText });
  await expect(sentMessage).toContainText(quoteText);

  await page.reload();
  await expect(messages.getByRole("listitem").filter({ hasText: replyText })).toContainText(quoteText);

  const unsentText = "This draft should stay local.";
  await page.getByRole("button", { name: "Reply to message 4", exact: true }).click();
  await expect(page.getByText("Replying to Grace: I can prepare the notes.")).toBeVisible();
  await composer.fill(unsentText);
  await page.getByRole("button", { name: "Cancel reply", exact: true }).click();

  await expect(page.getByText("Replying to Grace: I can prepare the notes.")).not.toBeVisible();
  await page.reload();
  await expect(messages.getByRole("listitem").filter({ hasText: replyText })).toContainText(quoteText);
  await expect(messages.getByRole("listitem").filter({ hasText: unsentText })).toHaveCount(0);
});

test("edits Ada's message in place and persists the edited marker", async ({ page }) => {
  const originalText = "Yes, all green since 02:00.";
  const updatedText = "Yes, all green since 03:00.";
  const adaMessage = page.getByRole("list", { name: "Messages", exact: true }).getByRole("listitem").filter({ hasText: "Ada:" });

  await page.getByRole("button", { name: "Edit message 2", exact: true }).click();
  await page.getByRole("textbox", { name: "Edit text of message 2", exact: true }).fill(updatedText);

  const editRequest = page.waitForRequest((request) => request.method() === "PATCH" && request.url().endsWith("/api/messages/2"));
  await page.getByRole("button", { name: "Save message 2", exact: true }).click();
  const request = await editRequest;
  expect(request.postDataJSON()).toEqual({ text: updatedText });

  await expect(adaMessage).toContainText(`${updatedText} (edited)`);
  await expect(adaMessage).not.toContainText(originalText);

  await page.reload();
  await expect(adaMessage).toContainText(`${updatedText} (edited)`);
  await expect(adaMessage).not.toContainText(originalText);
});
