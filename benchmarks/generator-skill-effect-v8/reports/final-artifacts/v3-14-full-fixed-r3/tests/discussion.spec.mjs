import { expect, test } from "@playwright/test";

const commentInput = (page) => page.getByLabel("Your comment");
const commentsList = (page) => page.getByRole("list", { name: "Comments" });
const commentWithText = (page, text) =>
  page.getByRole("listitem").filter({ has: page.getByText(text) });
const displayedCommentText = (page, text) => commentsList(page).getByText(new RegExp(`^#\\d+ ${text}$`));

async function resetAndOpen(page) {
  await page.request.post("/api/reset");
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Discussion" })).toBeVisible();
}

async function postComment(page, text) {
  const created = page.waitForRequest((request) => {
    if (request.method() !== "POST" || !request.url().endsWith("/api/comments")) return false;
    const body = request.postDataJSON();
    return body.text === text;
  });

  await commentInput(page).fill(text);
  await page.getByRole("button", { name: "Post" }).click();
  await created;
}

test.beforeEach(async ({ page }) => {
  await resetAndOpen(page);
});

test("posts comments and nests a reply under the replied-to comment", async ({ page }) => {
  await postComment(page, "First parent");

  await commentWithText(page, "First parent").getByRole("button", { name: /^Reply to comment #\d+$/ }).click();
  await postComment(page, "Reply to first parent");

  await postComment(page, "Second parent");

  await expect(page.getByText("3 comments")).toBeVisible();

  const firstParent = commentWithText(page, "First parent");
  const secondParent = commentWithText(page, "Second parent");
  await expect(
    firstParent.getByRole("list", { name: /^Replies to comment #\d+$/ }).getByText("Reply to first parent"),
  ).toBeVisible();
  await expect(displayedCommentText(page, "Second parent")).toBeVisible();
  await expect(secondParent.getByText("Reply to first parent")).toHaveCount(0);

  await page.reload();
  await expect(page.getByText("3 comments")).toBeVisible();
  await expect(displayedCommentText(page, "First parent")).toBeVisible();
  await expect(
    commentWithText(page, "First parent")
      .getByRole("list", { name: /^Replies to comment #\d+$/ })
      .getByText("Reply to first parent"),
  ).toBeVisible();
});

test("edits a comment in place and keeps the saved text after reload", async ({ page }) => {
  await postComment(page, "Draft wording");

  await commentWithText(page, "Draft wording").getByRole("button", { name: /^Edit comment #\d+$/ }).click();

  const editInput = page.getByLabel(/^New text for comment #\d+$/);
  const saved = page.waitForRequest((request) => {
    if (request.method() !== "PATCH" || !/\/api\/comments\/\d+$/.test(new URL(request.url()).pathname)) {
      return false;
    }
    return request.postDataJSON().text === "Published wording";
  });

  await editInput.fill("Published wording");
  await page.getByRole("button", { name: /^Save comment #\d+$/ }).click();
  await saved;

  await expect(commentsList(page).getByText("Published wording")).toBeVisible();

  await page.reload();
  await expect(commentsList(page).getByText("Published wording")).toBeVisible();
  await expect(commentsList(page).getByText("Draft wording")).toHaveCount(0);
});

test("keeps a comment when delete is dismissed and removes it when confirmed", async ({ page }) => {
  await postComment(page, "Delete candidate");

  page.once("dialog", async (dialog) => {
    expect(dialog.message()).toBe("Delete this comment?");
    await dialog.dismiss();
  });
  await commentWithText(page, "Delete candidate").getByRole("button", { name: /^Delete comment #\d+$/ }).click();

  await expect(commentsList(page).getByText("Delete candidate")).toBeVisible();
  await page.reload();
  await expect(commentsList(page).getByText("Delete candidate")).toBeVisible();

  const removed = page.waitForRequest(
    (request) => request.method() === "DELETE" && /\/api\/comments\/\d+$/.test(new URL(request.url()).pathname),
  );
  page.once("dialog", async (dialog) => {
    expect(dialog.message()).toBe("Delete this comment?");
    await dialog.accept();
  });
  await commentWithText(page, "Delete candidate").getByRole("button", { name: /^Delete comment #\d+$/ }).click();
  await removed;

  await expect(commentsList(page).getByText("Delete candidate")).toHaveCount(0);
  await expect(page.getByText("0 comments")).toBeVisible();

  await page.reload();
  await expect(commentsList(page).getByText("Delete candidate")).toHaveCount(0);
  await expect(page.getByText("0 comments")).toBeVisible();
});
