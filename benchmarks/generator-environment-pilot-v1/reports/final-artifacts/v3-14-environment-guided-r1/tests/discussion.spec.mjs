import { expect, test } from "@playwright/test";

const resetDiscussion = async (page) => {
  await page.request.post("/api/reset");
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Discussion", exact: true })).toBeVisible();
};

const postComment = async (page, text, parentId = null) => {
  const request = page.waitForRequest((req) => req.method() === "POST" && req.url().endsWith("/api/comments"));

  await page.getByLabel("Your comment").fill(text);
  await page.getByRole("button", { name: "Post", exact: true }).click();

  const posted = await request;
  expect(JSON.parse(posted.postData())).toEqual({ text, parentId });
};

test.beforeEach(async ({ page }) => {
  await resetDiscussion(page);
});

test("posts replies nested under their parent and counts replies", async ({ page }) => {
  await postComment(page, "Parent one");
  await postComment(page, "Parent two");

  const comments = page.getByRole("list", { name: "Comments", exact: true });
  const parentOne = comments.getByRole("listitem").filter({ hasText: "#1 Parent one" });
  const parentTwo = comments.getByRole("listitem").filter({ hasText: "#2 Parent two" });

  await parentOne.getByRole("button", { name: "Reply to comment #1", exact: true }).click();
  await postComment(page, "Reply to parent one", 1);

  await expect(page.getByText("3 comments")).toBeVisible();
  await expect(parentOne.getByRole("list", { name: "Replies to comment #1", exact: true })).toContainText("#3 Reply to parent one");
  await expect(parentTwo).not.toContainText("Reply to parent one");

  await page.reload();
  await expect(page.getByText("3 comments")).toBeVisible();
  await expect(parentOne.getByRole("list", { name: "Replies to comment #1", exact: true })).toContainText("#3 Reply to parent one");
  await expect(parentTwo).not.toContainText("Reply to parent one");
});

test("edits a comment in place and persists the saved text", async ({ page }) => {
  await postComment(page, "Original text");
  const originalText = page.getByText("Original text");
  await expect(originalText).toBeVisible();

  await page.getByRole("button", { name: "Edit comment #1", exact: true }).click();
  await page.getByLabel("New text for comment #1").fill("Edited text");

  const request = page.waitForRequest((req) => req.method() === "PATCH" && req.url().endsWith("/api/comments/1"));
  await page.getByRole("button", { name: "Save comment #1", exact: true }).click();
  const patch = await request;
  expect(JSON.parse(patch.postData())).toEqual({ text: "Edited text" });

  await expect(page.getByText("#1 Edited text")).toBeVisible();
  await page.reload();
  await expect(page.getByText("#1 Edited text")).toBeVisible();
  await expect(originalText).not.toBeVisible();
});

test("keeps a comment when delete is dismissed and removes it when confirmed", async ({ page }) => {
  await postComment(page, "Delete candidate");

  page.once("dialog", async (dialog) => {
    expect(dialog.message()).toBe("Delete this comment?");
    await dialog.dismiss();
  });
  await page.getByRole("button", { name: "Delete comment #1", exact: true }).click();
  await expect(page.getByText("#1 Delete candidate")).toBeVisible();

  await page.reload();
  await expect(page.getByText("#1 Delete candidate")).toBeVisible();

  page.once("dialog", async (dialog) => {
    expect(dialog.message()).toBe("Delete this comment?");
    await dialog.accept();
  });
  const request = page.waitForRequest((req) => req.method() === "DELETE" && req.url().endsWith("/api/comments/1"));
  await page.getByRole("button", { name: "Delete comment #1", exact: true }).click();
  await request;

  await expect(page.getByText("#1 Delete candidate")).not.toBeVisible();
  await page.reload();
  await expect(page.getByText("#1 Delete candidate")).not.toBeVisible();
});
