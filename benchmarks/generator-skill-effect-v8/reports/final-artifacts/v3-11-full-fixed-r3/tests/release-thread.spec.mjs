import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  await page.request.post("/api/reset");
  await page.goto("/");
});

test("shows seeded unread messages for Ada", async ({ page }) => {
  const messages = page.getByRole("list", { name: "Messages" });
  const divider = messages.getByText("2 new messages");

  await expect(page.getByRole("heading", { name: "Release thread (2 new)" })).toBeVisible();
  await expect(divider).toBeVisible();
  await expect(messages.getByRole("listitem")).toHaveCount(5);
  await expect(messages.getByRole("listitem").filter({ hasText: "Did the nightly build pass?" })).toBeVisible();
  await expect(messages.getByRole("listitem").filter({ hasText: "Yes, all green since 02:00." })).toBeVisible();
  await expect(messages.getByRole("listitem").filter({ hasText: "Then let's cut the release this afternoon." })).toBeVisible();
  await expect(messages.getByRole("listitem").filter({ hasText: "I can prepare the notes." })).toBeVisible();
});

test("marks unread messages as read and persists after reload", async ({ page }) => {
  const messages = page.getByRole("list", { name: "Messages" });
  const readRequest = page.waitForRequest((request) =>
    request.method() === "POST" && request.url().endsWith("/api/read")
  );

  await page.getByRole("button", { name: "Mark as read" }).click();
  await readRequest;

  await expect(page.getByRole("heading", { name: "Release thread", exact: true })).toBeVisible();
  await expect(messages.getByText("2 new messages")).not.toBeVisible();
  await expect(page.getByRole("button", { name: "Mark as read" })).not.toBeVisible();

  await page.reload();

  await expect(page.getByRole("heading", { name: "Release thread", exact: true })).toBeVisible();
  await expect(messages.getByText("2 new messages")).not.toBeVisible();
  await expect(page.getByRole("button", { name: "Mark as read" })).not.toBeVisible();
});

test("sends a reply with the selected quote and keeps it after reload", async ({ page }) => {
  const messages = page.getByRole("list", { name: "Messages" });
  const releaseMessage = messages.getByRole("listitem").filter({
    hasText: "Then let's cut the release this afternoon.",
  });

  await releaseMessage.getByRole("button", { name: "Reply to message 3" }).click();
  await expect(page.getByText("Replying to")).toBeVisible();
  await expect(page.getByText("Linus: Then let's cut the release this afternoon.", { exact: true })).toBeVisible();

  const createRequest = page.waitForRequest(async (request) => {
    if (request.method() !== "POST" || !request.url().endsWith("/api/messages")) return false;
    const body = request.postDataJSON();
    return body.text === "Shipping once notes are attached." &&
      body.quote === "Linus: Then let's cut the release this afternoon.";
  });

  await page.getByLabel("Your message").fill("Shipping once notes are attached.");
  await page.getByRole("button", { name: "Send" }).click();
  await createRequest;

  const sentReply = messages.getByRole("listitem").filter({ hasText: "Shipping once notes are attached." });
  await expect(sentReply).toContainText("Linus: Then let's cut the release this afternoon.");

  await page.reload();

  await expect(messages.getByRole("listitem").filter({ hasText: "Shipping once notes are attached." }))
    .toContainText("Linus: Then let's cut the release this afternoon.");
});

test("cancels a pending reply without sending a message", async ({ page }) => {
  const messages = page.getByRole("list", { name: "Messages" });
  const notesMessage = messages.getByRole("listitem").filter({ hasText: "I can prepare the notes." });

  await notesMessage.getByRole("button", { name: "Reply to message 4" }).click();
  await expect(page.getByText("Grace: I can prepare the notes.", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: "Cancel reply" }).click();

  await expect(page.getByText("Grace: I can prepare the notes.", { exact: true })).not.toBeVisible();
  await expect(messages.getByRole("listitem")).toHaveCount(5);

  await page.reload();

  await expect(messages.getByRole("listitem")).toHaveCount(5);
});

test("edits Ada's message in place and persists the edited marker", async ({ page }) => {
  const messages = page.getByRole("list", { name: "Messages" });
  const adaMessage = messages.getByRole("listitem").filter({ hasText: "Yes, all green since 02:00." });

  await adaMessage.getByRole("button", { name: "Edit message 2" }).click();

  const editRequest = page.waitForRequest(async (request) => {
    if (request.method() !== "PATCH" || !request.url().endsWith("/api/messages/2")) return false;
    return request.postDataJSON().text === "Yes, all green since 02:15 after the cache fix.";
  });

  await page.getByLabel("Edit text of message 2").fill("Yes, all green since 02:15 after the cache fix.");
  await page.getByRole("button", { name: "Save message 2" }).click();
  await editRequest;

  await expect(messages.getByRole("listitem").filter({
    hasText: "Yes, all green since 02:15 after the cache fix. (edited)",
  })).toBeVisible();

  await page.reload();

  await expect(messages.getByRole("listitem").filter({
    hasText: "Yes, all green since 02:15 after the cache fix. (edited)",
  })).toBeVisible();
});
