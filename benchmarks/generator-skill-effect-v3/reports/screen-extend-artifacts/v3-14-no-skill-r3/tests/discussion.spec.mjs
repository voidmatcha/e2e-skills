import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page, request }) => {
  await request.post("/api/reset");
  await page.goto("/");
});

async function post(page, text) {
  await page.getByLabel("Your comment").fill(text);
  await page.getByRole("button", { name: "Post" }).click();
  await expect(page.getByText(text)).toBeVisible();
}

test("posts a comment and keeps it after reload", async ({ page }) => {
  await expect(page.locator("#cm-count")).toHaveText("0 comments");
  await post(page, "Hello world");
  await expect(page.locator("#cm-count")).toHaveText("1 comment");
  await expect(page.getByLabel("Your comment")).toHaveValue("");

  await page.reload();
  await expect(page.getByText("Hello world")).toBeVisible();
  await expect(page.locator("#cm-count")).toHaveText("1 comment");
});

test("does not post a blank comment", async ({ page }) => {
  await page.getByLabel("Your comment").fill("   ");
  await page.getByRole("button", { name: "Post" }).click();
  await expect(page.locator("#cm-count")).toHaveText("0 comments");
  await expect(page.getByRole("list", { name: "Comments" }).locator("li")).toHaveCount(0);
});

test("nests a reply under the comment it answers and counts it", async ({ page }) => {
  await post(page, "First");
  await post(page, "Second");

  await page.getByRole("button", { name: "Reply to comment #2" }).click();
  await expect(page.getByLabel("Your comment")).toHaveAttribute("placeholder", "Replying to #2");
  await post(page, "Answer to second");

  await expect(page.locator("#cm-count")).toHaveText("3 comments");
  const replies = page.getByRole("list", { name: "Replies to comment #2" });
  await expect(replies.getByText("Answer to second")).toBeVisible();
  await expect(page.getByRole("list", { name: "Replies to comment #1" })).toHaveCount(0);

  await page.reload();
  await expect(page.locator("#cm-count")).toHaveText("3 comments");
  await expect(
    page.getByRole("list", { name: "Replies to comment #2" }).getByText("Answer to second"),
  ).toBeVisible();
  await expect(page.getByRole("list", { name: "Replies to comment #1" })).toHaveCount(0);
});

test("edits a comment in place and keeps the edit after reload", async ({ page }) => {
  await post(page, "Original");
  await page.getByRole("button", { name: "Edit comment #1" }).click();
  await page.getByLabel("New text for comment #1").fill("Changed");
  await page.getByRole("button", { name: "Save comment #1" }).click();

  await expect(page.getByText("Changed")).toBeVisible();
  await expect(page.getByText("Original")).toHaveCount(0);
  await expect(page.locator("#cm-count")).toHaveText("1 comment");

  await page.reload();
  await expect(page.getByText("Changed")).toBeVisible();
  await expect(page.getByText("Original")).toHaveCount(0);
});

test("deletes a comment after accepting the dialog", async ({ page }) => {
  await post(page, "Keep me");
  await post(page, "Remove me");

  let message;
  page.once("dialog", (dialog) => {
    message = dialog.message();
    dialog.accept();
  });
  await page.getByRole("button", { name: "Delete comment #2" }).click();

  await expect(page.getByText("Remove me")).toHaveCount(0);
  expect(message).toBe("Delete this comment?");
  await expect(page.locator("#cm-count")).toHaveText("1 comment");

  await page.reload();
  await expect(page.getByText("Keep me")).toBeVisible();
  await expect(page.getByText("Remove me")).toHaveCount(0);
});

test("keeps a comment when the delete dialog is dismissed", async ({ page }) => {
  await post(page, "Still here");
  page.once("dialog", (dialog) => dialog.dismiss());
  await page.getByRole("button", { name: "Delete comment #1" }).click();

  await expect(page.getByText("Still here")).toBeVisible();
  await expect(page.locator("#cm-count")).toHaveText("1 comment");

  await page.reload();
  await expect(page.getByText("Still here")).toBeVisible();
});

test("deleting a comment removes its replies from the count", async ({ page }) => {
  await post(page, "Parent");
  await page.getByRole("button", { name: "Reply to comment #1" }).click();
  await post(page, "Child");
  await expect(page.locator("#cm-count")).toHaveText("2 comments");

  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "Delete comment #1" }).click();
  await expect(page.locator("#cm-count")).toHaveText("0 comments");

  await page.reload();
  await expect(page.locator("#cm-count")).toHaveText("0 comments");
});
