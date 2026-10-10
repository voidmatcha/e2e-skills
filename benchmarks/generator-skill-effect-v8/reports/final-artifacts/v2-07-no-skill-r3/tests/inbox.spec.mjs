import { expect, test } from "@playwright/test";

const messages = {
  ada: {
    from: "Ada",
    subject: "Lunch on Friday?",
    body: "Shall we try the new place by the river?",
  },
  grace: {
    from: "Grace",
    subject: "Compiler notes",
    body: "Attached are the notes from yesterday's session.",
  },
  linus: {
    from: "Linus",
    subject: "Patch review",
    body: "Please look at the second hunk; the first is fine.",
  },
  margaret: {
    from: "Margaret",
    subject: "Launch checklist",
    body: "Everything is green except the backup drill.",
  },
};

const heading = (page, unread) => page.getByRole("heading", { name: `Inbox (${unread})` });
const messageList = (page) => page.getByRole("list", { name: "Messages" });
const messageButton = (page, subject) => page.getByRole("button", { name: new RegExp(`^Open (unread )?${escapeRegExp(subject)}$`) });
const unreadMessageButton = (page, subject) => page.getByRole("button", { name: `Open unread ${subject}` });
const readMessageButton = (page, subject) => page.getByRole("button", { name: `Open ${subject}` });

function escapeRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

test.beforeEach(async ({ request }) => {
  await request.post("/api/reset");
});

test("shows the seeded inbox with three unread messages", async ({ page }) => {
  await page.goto("/");

  await expect(heading(page, 3)).toBeVisible();
  await expect(messageList(page).getByRole("listitem")).toHaveCount(4);
  await expect(page.locator(".message.unread")).toHaveCount(3);
  await expect(unreadMessageButton(page, messages.ada.subject)).toBeVisible();
  await expect(unreadMessageButton(page, messages.grace.subject)).toBeVisible();
  await expect(readMessageButton(page, messages.linus.subject)).toBeVisible();
  await expect(unreadMessageButton(page, messages.margaret.subject)).toBeVisible();
});

test("opening a message shows its details and marks only that message read", async ({ page }) => {
  await page.goto("/");

  await messageButton(page, messages.ada.subject).click();

  const reader = page.getByRole("article", { name: "Message" });
  await expect(page.getByRole("heading", { name: messages.ada.subject })).toBeVisible();
  await expect(reader.getByText(`From ${messages.ada.from}`)).toBeVisible();
  await expect(reader.getByText(messages.ada.body)).toBeVisible();
  await expect(heading(page, 2)).toBeVisible();
  await expect(page.locator(".message.unread")).toHaveCount(2);
  await expect(readMessageButton(page, messages.ada.subject)).toBeVisible();
  await expect(unreadMessageButton(page, messages.grace.subject)).toBeVisible();
  await expect(readMessageButton(page, messages.linus.subject)).toBeVisible();
  await expect(unreadMessageButton(page, messages.margaret.subject)).toBeVisible();
});

test("mark all read clears the unread count and markers", async ({ page }) => {
  await page.goto("/");

  await page.getByRole("button", { name: "Mark all read" }).click();

  await expect(heading(page, 0)).toBeVisible();
  await expect(page.locator(".message.unread")).toHaveCount(0);
  await expect(readMessageButton(page, messages.ada.subject)).toBeVisible();
  await expect(readMessageButton(page, messages.grace.subject)).toBeVisible();
  await expect(readMessageButton(page, messages.linus.subject)).toBeVisible();
  await expect(readMessageButton(page, messages.margaret.subject)).toBeVisible();
});

test("unread only filter hides read messages", async ({ page }) => {
  await page.goto("/");

  await page.getByRole("checkbox", { name: "Unread only" }).check();

  await expect(messageList(page).getByRole("listitem")).toHaveCount(3);
  await expect(unreadMessageButton(page, messages.ada.subject)).toBeVisible();
  await expect(unreadMessageButton(page, messages.grace.subject)).toBeVisible();
  await expect(readMessageButton(page, messages.linus.subject)).toBeHidden();
  await expect(unreadMessageButton(page, messages.margaret.subject)).toBeVisible();
});

test("read state persists after reload", async ({ page }) => {
  await page.goto("/");

  await messageButton(page, messages.grace.subject).click();
  await expect(heading(page, 2)).toBeVisible();

  await page.reload();

  await expect(heading(page, 2)).toBeVisible();
  await expect(readMessageButton(page, messages.grace.subject)).toBeVisible();
  await expect(unreadMessageButton(page, messages.ada.subject)).toBeVisible();
  await expect(readMessageButton(page, messages.linus.subject)).toBeVisible();
  await expect(unreadMessageButton(page, messages.margaret.subject)).toBeVisible();
  await expect(page.locator(".message.unread")).toHaveCount(2);
});
