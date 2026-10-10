import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  await page.request.post("/api/reset");
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Discussion", exact: true })).toBeVisible();
});

async function postComment(page, text) {
  const responsePromise = page.waitForResponse(
    (response) => response.url().endsWith("/api/comments") && response.request().method() === "POST"
  );
  await page.getByLabel("Your comment").fill(text);
  await page.getByRole("button", { name: "Post", exact: true }).click();
  await expect.poll(async () => (await responsePromise).status()).toBe(201);
}

test("posts a comment and keeps it after reload", async ({ page }) => {
  await postComment(page, "This is a persisted top-level comment");

  await expect(page.getByText("#1 This is a persisted top-level comment")).toBeVisible();
  await expect(page.getByText(/^1 comment$/)).toBeVisible();

  await page.reload();

  await expect(page.getByText("#1 This is a persisted top-level comment")).toBeVisible();
  await expect(page.getByText(/^1 comment$/)).toBeVisible();
});

test("nests a reply under the replied-to comment and counts replies", async ({ page }) => {
  await postComment(page, "First parent");
  await postComment(page, "Second parent");

  await page.getByRole("button", { name: "Reply to comment #1", exact: true }).click();
  await postComment(page, "Nested reply to the first parent");

  const firstReplies = page.getByRole("list", { name: "Replies to comment #1", exact: true });
  const secondParent = page.getByRole("listitem").filter({ hasText: "#2 Second parent" });
  await expect(firstReplies.getByText("#3 Nested reply to the first parent")).toBeVisible();
  await expect(secondParent).toBeVisible();
  await expect(secondParent.getByText("#3 Nested reply to the first parent")).not.toBeVisible();
  await expect(page.getByText(/^3 comments$/)).toBeVisible();

  await page.reload();

  await expect(
    page.getByRole("list", { name: "Replies to comment #1", exact: true }).getByText("#3 Nested reply to the first parent")
  ).toBeVisible();
  await expect(page.getByText(/^3 comments$/)).toBeVisible();
});

test("edits a comment in place and saves the new text", async ({ page }) => {
  await postComment(page, "Original editable text");

  const originalComment = page.getByText("#1 Original editable text");
  await expect(originalComment).toBeVisible();
  await page.getByRole("button", { name: "Edit comment #1", exact: true }).click();
  await page.getByLabel("New text for comment #1").fill("Edited persisted text");
  const responsePromise = page.waitForResponse(
    (response) => response.url().endsWith("/api/comments/1") && response.request().method() === "PATCH"
  );
  await page.getByRole("button", { name: "Save comment #1", exact: true }).click();
  await expect.poll(async () => (await responsePromise).status()).toBe(200);

  await expect(page.getByText("#1 Edited persisted text")).toBeVisible();
  await expect(originalComment).not.toBeVisible();

  await page.reload();

  await expect(page.getByText("#1 Edited persisted text")).toBeVisible();
});

test("dismisses and confirms deletion from the browser dialog", async ({ page }) => {
  await postComment(page, "Comment that survives dismissal");
  await postComment(page, "Comment that will be deleted");

  const deletedComment = page.getByText("#2 Comment that will be deleted");
  await expect(deletedComment).toBeVisible();
  page.once("dialog", async (dialog) => {
    expect(dialog.message()).toBe("Delete this comment?");
    await dialog.dismiss();
  });
  await page.getByRole("button", { name: "Delete comment #1", exact: true }).click();

  await expect(page.getByText("#1 Comment that survives dismissal")).toBeVisible();

  page.once("dialog", async (dialog) => {
    expect(dialog.message()).toBe("Delete this comment?");
    await dialog.accept();
  });
  const responsePromise = page.waitForResponse(
    (response) => response.url().endsWith("/api/comments/2") && response.request().method() === "DELETE"
  );
  await page.getByRole("button", { name: "Delete comment #2", exact: true }).click();
  await expect.poll(async () => (await responsePromise).status()).toBe(200);

  await expect(page.getByText("#1 Comment that survives dismissal")).toBeVisible();
  await expect(deletedComment).not.toBeVisible();
  await expect(page.getByText(/^1 comment$/)).toBeVisible();

  await page.reload();

  await expect(page.getByText("#1 Comment that survives dismissal")).toBeVisible();
  await expect(deletedComment).not.toBeVisible();
});
