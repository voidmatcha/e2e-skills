import { expect, test } from "@playwright/test";

const resetDiscussion = async (page) => {
  await page.request.post("/api/reset");
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Discussion", exact: true })).toBeVisible();
};

const requestBody = (request) => JSON.parse(request.postData() ?? "{}");

const postComment = async (page, text, parentId = null) => {
  const created = page.waitForRequest((request) => {
    if (request.method() !== "POST" || !request.url().endsWith("/api/comments")) {
      return false;
    }

    const body = requestBody(request);
    return body.text === text && body.parentId === parentId;
  });

  await page.getByLabel("Your comment").fill(text);
  await page.getByRole("button", { name: "Post", exact: true }).click();
  await created;
};

test.beforeEach(async ({ page }) => {
  await resetDiscussion(page);
});

test("posts comments and nests a reply under the selected comment", async ({ page }) => {
  await postComment(page, "Alpha root");
  await postComment(page, "Beta root");

  const thread = page.getByRole("list", { name: "Comments", exact: true });
  const alphaComment = thread.getByRole("listitem").filter({ hasText: "#1 Alpha root" });
  const betaComment = thread.getByRole("listitem").filter({ hasText: "#2 Beta root" });

  await alphaComment.getByRole("button", { name: "Reply to comment #1", exact: true }).click();
  await postComment(page, "Nested under alpha", 1);

  await expect(page.getByText("3 comments")).toBeVisible();
  await expect(
    alphaComment
      .getByRole("list", { name: "Replies to comment #1", exact: true })
      .getByRole("listitem")
      .filter({ hasText: "#3 Nested under alpha" }),
  ).toBeVisible();
  await expect(betaComment).toHaveText("#2 Beta rootReplyEditDelete");

  await page.reload();
  await expect(page.getByText("3 comments")).toBeVisible();
  await expect(
    page
      .getByRole("list", { name: "Comments", exact: true })
      .getByRole("listitem")
      .filter({ hasText: "#1 Alpha root" })
      .getByRole("list", { name: "Replies to comment #1", exact: true })
      .getByRole("listitem")
      .filter({ hasText: "#3 Nested under alpha" }),
  ).toBeVisible();
});

test("edits a comment in place and keeps the saved text after reload", async ({ page }) => {
  await postComment(page, "Original text");

  await page.getByRole("button", { name: "Edit comment #1", exact: true }).click();
  await page.getByLabel("New text for comment #1").fill("Edited text");

  const saved = page.waitForRequest((request) => {
    if (request.method() !== "PATCH" || !request.url().endsWith("/api/comments/1")) {
      return false;
    }

    return requestBody(request).text === "Edited text";
  });
  await page.getByRole("button", { name: "Save comment #1", exact: true }).click();
  await saved;

  await expect(page.getByText("#1 Edited text")).toBeVisible();

  await page.reload();
  await expect(page.getByText("#1 Edited text")).toBeVisible();
});

test("dismisses and confirms deletion dialogs with persisted results", async ({ page }) => {
  await postComment(page, "Delete candidate");

  const comment = page
    .getByRole("list", { name: "Comments", exact: true })
    .getByRole("listitem")
    .filter({ hasText: "#1 Delete candidate" });

  const dismissedDialog = new Promise((resolve) => {
    page.once("dialog", async (dialog) => {
      resolve(dialog.message());
      await dialog.dismiss();
    });
  });
  await comment.getByRole("button", { name: "Delete comment #1", exact: true }).click();
  await expect(dismissedDialog).resolves.toBe("Delete this comment?");
  await expect(comment).toBeVisible();

  await page.reload();
  await expect(page.getByText("#1 Delete candidate")).toBeVisible();

  const deleted = page.waitForRequest(
    (request) => request.method() === "DELETE" && request.url().endsWith("/api/comments/1"),
  );
  const acceptedDialog = new Promise((resolve) => {
    page.once("dialog", async (dialog) => {
      resolve(dialog.message());
      await dialog.accept();
    });
  });
  await page.getByRole("button", { name: "Delete comment #1", exact: true }).click();
  await expect(acceptedDialog).resolves.toBe("Delete this comment?");
  await deleted;

  await expect(page.getByText("#1 Delete candidate")).toHaveCount(0);

  await page.reload();
  await expect(page.getByText("#1 Delete candidate")).toHaveCount(0);
  await expect(page.getByText("0 comments")).toBeVisible();
});
