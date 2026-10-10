import { expect, test } from "@playwright/test";

const messageList = (page) => page.getByRole("list", { name: "Messages", exact: true });
const messageItem = (page, text) => messageList(page).getByRole("listitem").filter({ hasText: text });
// JUSTIFIED: the reply banner has no role, label, or stable text-only wrapper.
const replyBanner = (page) => page.locator("#th-quote");

const isRequest = (request, method, pathname) => {
  const url = new URL(request.url());
  return request.method() === method && url.pathname === pathname;
};

test.beforeEach(async ({ page, request }) => {
  await request.post("/api/reset");
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Release thread (2 new)", exact: true })).toBeVisible();
});

test("shows seeded unread messages and persists marking them read", async ({ page }) => {
  await expect(messageItem(page, "Grace: Did the nightly build pass?")).toBeVisible();
  await expect(messageItem(page, "Ada: Yes, all green since 02:00.")).toBeVisible();
  await expect(messageItem(page, "Linus: Then let's cut the release this afternoon.")).toBeVisible();
  await expect(messageItem(page, "Grace: I can prepare the notes.")).toBeVisible();
  await expect(messageList(page).getByText("2 new messages")).toBeVisible();

  const markReadButton = page.getByRole("button", { name: "Mark as read", exact: true });
  await expect(markReadButton).toBeVisible();
  const markReadRequest = page.waitForRequest((request) => isRequest(request, "POST", "/api/read"));
  await markReadButton.click();
  await markReadRequest;

  await expect(page.getByRole("heading", { name: "Release thread", exact: true })).toBeVisible();
  await expect(messageList(page).getByText("2 new messages")).not.toBeVisible();
  await expect(markReadButton).toBeHidden();

  await page.reload();
  await expect(page.getByRole("heading", { name: "Release thread", exact: true })).toBeVisible();
  await expect(messageList(page).getByText("2 new messages")).not.toBeVisible();
  await expect(markReadButton).toBeHidden();
});

test("sends a quoted reply and cancels a pending reply without sending", async ({ page }) => {
  await expect(messageList(page).getByRole("listitem")).toHaveCount(5);
  await page.getByRole("button", { name: "Reply to message 3", exact: true }).click();
  await expect(replyBanner(page)).toBeVisible();
  await expect(replyBanner(page)).toContainText("Linus: Then let's cut the release this afternoon.");

  await page.getByLabel("Your message").fill("Cancel reply should not send");
  await page.getByRole("button", { name: "Cancel reply", exact: true }).click();
  await expect(replyBanner(page)).not.toBeVisible();
  await expect(messageList(page).getByRole("listitem")).toHaveCount(5);

  await page.getByRole("button", { name: "Reply to message 3", exact: true }).click();
  await page.getByLabel("Your message").fill("I'll stage the release candidate.");

  const sendRequest = page.waitForRequest((request) => isRequest(request, "POST", "/api/messages"));
  await page.getByRole("button", { name: "Send", exact: true }).click();
  const request = await sendRequest;
  expect(request.postDataJSON()).toEqual({
    text: "I'll stage the release candidate.",
    quote: "Linus: Then let's cut the release this afternoon.",
  });

  const reply = messageItem(page, "Ada: I'll stage the release candidate.");
  await expect(reply).toBeVisible();
  await expect(reply.getByText("Linus: Then let's cut the release this afternoon.", { exact: true })).toBeVisible();
  await expect(replyBanner(page)).not.toBeVisible();

  await page.reload();
  await expect(messageItem(page, "Ada: I'll stage the release candidate.")).toBeVisible();
  await expect(messageItem(page, "Ada: I'll stage the release candidate.").getByText("Linus: Then let's cut the release this afternoon.", { exact: true })).toBeVisible();
});

test("edits Ada's message in place and persists the edited marker", async ({ page }) => {
  await expect(messageItem(page, "Ada: Yes, all green since 02:00.")).toBeVisible();
  await page.getByRole("button", { name: "Edit message 2", exact: true }).click();
  await page.getByLabel("Edit text of message 2").fill("Yes, all green since 02:30.");

  const editRequest = page.waitForRequest((request) => isRequest(request, "PATCH", "/api/messages/2"));
  await page.getByRole("button", { name: "Save message 2", exact: true }).click();
  const request = await editRequest;
  expect(request.postDataJSON()).toEqual({ text: "Yes, all green since 02:30." });

  await expect(messageItem(page, "Ada: Yes, all green since 02:30. (edited)")).toBeVisible();
  await expect(messageItem(page, "Ada: Yes, all green since 02:00.")).toHaveCount(0);

  await page.reload();
  await expect(messageItem(page, "Ada: Yes, all green since 02:30. (edited)")).toBeVisible();
  await expect(messageItem(page, "Ada: Yes, all green since 02:00.")).toHaveCount(0);
});
