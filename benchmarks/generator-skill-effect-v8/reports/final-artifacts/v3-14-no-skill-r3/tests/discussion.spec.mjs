import { expect, test } from "@playwright/test";

test.beforeEach(async ({ request }) => {
  await request.post("/api/reset");
});

test("posts, replies, edits, deletes, and persists discussion comments", async ({ page }) => {
  await page.goto("/");

  await page.getByLabel("Your comment").fill("First comment");
  await page.getByRole("button", { name: "Post" }).click();
  await page.getByLabel("Your comment").fill("Second comment");
  await page.getByRole("button", { name: "Post" }).click();

  await page.getByRole("button", { name: "Reply to comment #1" }).click();
  await page.getByLabel("Your comment").fill("Reply to the first comment");
  await page.getByRole("button", { name: "Post" }).click();

  const firstComment = page.locator('li.comment[data-id="1"]');
  const secondComment = page.locator('li.comment[data-id="2"]');
  const firstReplies = firstComment.getByRole("list", { name: "Replies to comment #1" });

  await expect(page.locator("#cm-count")).toHaveText("3 comments");
  await expect(firstComment.locator(".text").first()).toHaveText("#1 First comment");
  await expect(secondComment.locator(".text")).toHaveText("#2 Second comment");
  await expect(firstReplies.locator('li.comment[data-id="3"] .text')).toHaveText(
    "#3 Reply to the first comment",
  );
  await expect(secondComment.getByRole("list", { name: "Replies to comment #2" })).toHaveCount(0);
  await expect(secondComment).not.toContainText("Reply to the first comment");

  await page.getByRole("button", { name: "Edit comment #1" }).click();
  await page.getByLabel("New text for comment #1").fill("Edited first comment");
  await page.getByRole("button", { name: "Save comment #1" }).click();
  await expect(firstComment.locator(".text").first()).toHaveText("#1 Edited first comment");

  await page.reload();
  await expect(page.locator("#cm-count")).toHaveText("3 comments");
  await expect(page.locator('li.comment[data-id="1"] .text').first()).toHaveText(
    "#1 Edited first comment",
  );
  await expect(
    page
      .locator('li.comment[data-id="1"]')
      .getByRole("list", { name: "Replies to comment #1" })
      .locator('li.comment[data-id="3"] .text'),
  ).toHaveText("#3 Reply to the first comment");
  await expect(page.locator('li.comment[data-id="2"] .text')).toHaveText("#2 Second comment");

  page.once("dialog", async (dialog) => {
    await dialog.dismiss();
  });
  await page.getByRole("button", { name: "Delete comment #2" }).click();
  await expect(page.locator('li.comment[data-id="2"] .text')).toHaveText("#2 Second comment");
  await expect(page.locator("#cm-count")).toHaveText("3 comments");

  await page.reload();
  await expect(page.locator('li.comment[data-id="2"] .text')).toHaveText("#2 Second comment");

  page.once("dialog", async (dialog) => {
    await dialog.accept();
  });
  await page.getByRole("button", { name: "Delete comment #2" }).click();
  await expect(page.locator('li.comment[data-id="2"]')).toHaveCount(0);
  await expect(page.locator("#cm-count")).toHaveText("2 comments");

  await page.reload();
  await expect(page.locator('li.comment[data-id="2"]')).toHaveCount(0);
  await expect(page.locator("#cm-count")).toHaveText("2 comments");
  await expect(page.locator('li.comment[data-id="1"] .text').first()).toHaveText(
    "#1 Edited first comment",
  );
  await expect(
    page
      .locator('li.comment[data-id="1"]')
      .getByRole("list", { name: "Replies to comment #1" })
      .locator('li.comment[data-id="3"] .text'),
  ).toHaveText("#3 Reply to the first comment");
});
