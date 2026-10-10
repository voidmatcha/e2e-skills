import { expect, test } from "@playwright/test";

const comment = (page, id) => page.locator(`li.comment[data-id="${id}"]`);
const commentText = (page, id) => comment(page, id).locator(":scope > p.text");
const repliesTo = (page, id) => comment(page, id).locator(`:scope > ul[aria-label="Replies to comment #${id}"]`);

async function postComment(page, text) {
  await page.getByLabel("Your comment").fill(text);
  await page.getByRole("button", { name: "Post" }).click();
}

test.beforeEach(async ({ request }) => {
  await request.post("/api/reset");
});

test("posts comments and nests replies under the selected comment", async ({ page }) => {
  await page.goto("/");

  await postComment(page, "Parent one");
  await postComment(page, "Parent two");
  await page.getByRole("button", { name: "Reply to comment #1" }).click();
  await postComment(page, "Reply to parent one");

  await expect(page.locator("#cm-count")).toHaveText("3 comments");
  await expect(commentText(page, 1)).toHaveText("#1 Parent one");
  await expect(commentText(page, 2)).toHaveText("#2 Parent two");
  await expect(repliesTo(page, 1).locator(":scope > li.comment")).toHaveCount(1);
  await expect(repliesTo(page, 1).locator(':scope > li.comment[data-id="3"] > p.text')).toHaveText("#3 Reply to parent one");
  await expect(comment(page, 2).locator(':scope > ul[aria-label="Replies to comment #2"]')).toHaveCount(0);

  await page.reload();

  await expect(page.locator("#cm-count")).toHaveText("3 comments");
  await expect(repliesTo(page, 1).locator(':scope > li.comment[data-id="3"] > p.text')).toHaveText("#3 Reply to parent one");
  await expect(comment(page, 2).locator(':scope > ul[aria-label="Replies to comment #2"]')).toHaveCount(0);
});

test("edits a comment in place and keeps the edit after reload", async ({ page }) => {
  await page.goto("/");

  await postComment(page, "Original text");
  await page.getByRole("button", { name: "Edit comment #1" }).click();
  await page.getByLabel("New text for comment #1").fill("Updated text");
  await page.getByRole("button", { name: "Save comment #1" }).click();

  await expect(commentText(page, 1)).toHaveText("#1 Updated text");

  await page.reload();

  await expect(commentText(page, 1)).toHaveText("#1 Updated text");
});

test("keeps a comment when delete is dismissed and removes it when confirmed", async ({ page }) => {
  await page.goto("/");

  await postComment(page, "Keep me first");

  page.once("dialog", async (dialog) => {
    expect(dialog.message()).toBe("Delete this comment?");
    await dialog.dismiss();
  });
  await page.getByRole("button", { name: "Delete comment #1" }).click();

  await expect(commentText(page, 1)).toHaveText("#1 Keep me first");

  page.once("dialog", async (dialog) => {
    expect(dialog.message()).toBe("Delete this comment?");
    await dialog.accept();
  });
  await page.getByRole("button", { name: "Delete comment #1" }).click();

  await expect(comment(page, 1)).toHaveCount(0);

  await page.reload();

  await expect(comment(page, 1)).toHaveCount(0);
  await expect(page.locator("#cm-count")).toHaveText("0 comments");
});
