import { expect, test } from "@playwright/test";

const commentText = (id, text) => `#${id} ${text}`;

async function resetDiscussion(request) {
  const response = await request.post("/api/reset");
  expect(response.ok()).toBeTruthy();
}

function commentItem(page, id, text) {
  return page.getByRole("listitem").filter({
    has: page.getByText(commentText(id, text)),
  });
}

function writeRequest(page, method, path, payload) {
  return page.waitForRequest((request) => {
    if (request.method() !== method || !request.url().endsWith(path)) {
      return false;
    }

    return JSON.stringify(request.postDataJSON()) === JSON.stringify(payload);
  });
}

async function postComment(page, text, parentId = null) {
  const requestPromise = writeRequest(page, "POST", "/api/comments", {
    text,
    parentId,
  });

  await page.getByLabel("Your comment").fill(text);
  await page.getByRole("button", { name: "Post", exact: true }).click();
  await requestPromise;
}

test.beforeEach(async ({ page, request }) => {
  await resetDiscussion(request);
  await page.goto("/");
  await expect(page.getByText("0 comments")).toBeVisible();
});

test.afterEach(async ({ request }) => {
  await resetDiscussion(request);
});

test("stores comments, nested replies, edits, and confirmed deletions", async ({
  page,
}) => {
  await postComment(page, "Parent one");
  await postComment(page, "Parent two");

  await page
    .getByRole("button", { name: "Reply to comment #1", exact: true })
    .click();
  await expect(page.getByLabel("Your comment")).toHaveAttribute(
    "placeholder",
    "Replying to #1",
  );
  await postComment(page, "Reply for parent one", 1);

  const firstComment = commentItem(page, 1, "Parent one");
  const secondComment = commentItem(page, 2, "Parent two");
  const reply = page.getByText(commentText(3, "Reply for parent one"), {
    exact: true,
  });

  await expect(firstComment.getByRole("list", { name: "Replies to comment #1" }))
    .toContainText(commentText(3, "Reply for parent one"));
  await expect(secondComment).not.toContainText("Reply for parent one");
  await expect(page.getByText("3 comments")).toBeVisible();

  const patchPromise = writeRequest(page, "PATCH", "/api/comments/1", {
    text: "Parent one edited",
  });
  await firstComment.getByRole("button", { name: "Edit comment #1" }).click();
  await page
    .getByRole("textbox", { name: "New text for comment #1" })
    .fill("Parent one edited");
  await page
    .getByRole("button", { name: "Save comment #1", exact: true })
    .click();
  await patchPromise;
  await expect(page.getByText(commentText(1, "Parent one edited"))).toBeVisible();

  page.once("dialog", async (dialog) => {
    expect(dialog.message()).toBe("Delete this comment?");
    await dialog.dismiss();
  });
  await secondComment.getByRole("button", { name: "Delete comment #2" }).click();
  await expect(secondComment).toBeVisible();

  await page.reload();
  await expect(page.getByText(commentText(1, "Parent one edited"))).toBeVisible();
  await expect(reply).toBeVisible();
  await expect(secondComment).toBeVisible();
  await expect(page.getByText("3 comments")).toBeVisible();

  const deletePromise = writeRequest(page, "DELETE", "/api/comments/2", null);
  page.once("dialog", async (dialog) => {
    expect(dialog.message()).toBe("Delete this comment?");
    await dialog.accept();
  });
  await secondComment.getByRole("button", { name: "Delete comment #2" }).click();
  await deletePromise;

  await expect(page.getByText(commentText(2, "Parent two"))).toHaveCount(0);
  await page.reload();
  await expect(page.getByText(commentText(1, "Parent one edited"))).toBeVisible();
  await expect(reply).toBeVisible();
  await expect(page.getByText(commentText(2, "Parent two"))).toHaveCount(0);
  await expect(page.getByText("2 comments")).toBeVisible();
});
