import { expect, test } from "@playwright/test";

const messages = (page) => page.getByRole("list", { name: "Messages" }).getByRole("listitem");
const heading = (page) => page.getByRole("heading", { level: 1 });
const composer = (page) => page.getByRole("textbox", { name: "Your message" });

test.beforeEach(async ({ page }) => {
  await page.request.post("/api/reset");
  await page.goto("/");
  await expect(heading(page)).toHaveText("Release thread (2 new)");
});

test("the unread divider and mark as read persist", async ({ page }) => {
  await expect(messages(page)).toHaveCount(5);
  await expect(messages(page).nth(2)).toHaveText("2 new messages");
  await expect(messages(page).nth(3)).toContainText("Linus:");
  await page.getByRole("button", { name: "Mark as read" }).click();
  await expect(heading(page)).toHaveText("Release thread");
  await expect(page.getByText("2 new messages")).toBeHidden();
  await page.reload();
  await expect(heading(page)).toHaveText("Release thread");
  await expect(messages(page)).toHaveCount(4);
});

test("reply carries the quote and cancel reply drops it", async ({ page }) => {
  await page.getByRole("button", { name: "Reply to message 3" }).click();
  await expect(page.getByText("Replying to")).toBeVisible();
  await expect(page.getByText("Linus: Then let's cut the release this afternoon.").nth(1)).toBeVisible();
  await page.getByRole("button", { name: "Cancel reply" }).click();
  await expect(page.getByText("Replying to")).toBeHidden();
  await composer(page).fill("Sounds good.");
  await page.getByRole("button", { name: "Send" }).click();
  await expect(messages(page).last()).toContainText("Ada: Sounds good.");
  await expect(messages(page).last().locator("blockquote")).toHaveCount(0);
  await page.getByRole("button", { name: "Reply to message 1" }).click();
  await composer(page).fill("Yes, see above.");
  await page.getByRole("button", { name: "Send" }).click();
  await expect(messages(page).last()).toContainText("Ada: Yes, see above.");
  await expect(messages(page).last().getByRole("blockquote")).toHaveText("Grace: Did the nightly build pass?");
  await page.reload();
  await expect(messages(page).last().getByRole("blockquote")).toHaveText("Grace: Did the nightly build pass?");
});

test("editing an own message marks it edited and persists", async ({ page }) => {
  await page.getByRole("button", { name: "Edit message 2" }).click();
  await page.getByRole("textbox", { name: "Edit text of message 2" }).fill("Yes, all green since 02:15.");
  await page.getByRole("button", { name: "Save message 2" }).click();
  await expect(messages(page).nth(1)).toContainText("Ada: Yes, all green since 02:15. (edited)");
  await expect(page.getByRole("button", { name: "Edit message 1" })).toHaveCount(0);
  await page.reload();
  await expect(messages(page).nth(1)).toContainText("Yes, all green since 02:15. (edited)");
});
