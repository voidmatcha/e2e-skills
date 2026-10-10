import { expect, test } from "@playwright/test";

const thread = (page) => page.getByRole("list", { name: "Comments" });
const topLevel = (page) => page.locator("ul[aria-label='Comments'] > li");

async function post(page, text) {
  await page.getByLabel("Your comment").fill(text);
  await page.getByRole("button", { name: "Post" }).click();
  await expect(page.getByText(text)).toBeVisible();
}

test.beforeEach(async ({ page }) => {
  await page.request.post("/api/reset");
  await page.goto("/");
  await expect(page.getByText("0 comments")).toBeVisible();
});

test("posts comments and counts replies", async ({ page }) => {
  await post(page, "First thought");
  await expect(page.getByText("1 comment", { exact: true })).toBeVisible();
  await post(page, "Second thought");
  await page.getByRole("button", { name: "Reply to comment #2" }).click();
  await post(page, "A reply");
  await expect(page.getByText("3 comments")).toBeVisible();
});

test("a reply is nested under the comment replied to", async ({ page }) => {
  await post(page, "Alpha");
  await post(page, "Beta");
  await page.getByRole("button", { name: "Reply to comment #2" }).click();
  await post(page, "Reply to Beta");
  await expect(page.getByRole("list", { name: "Replies to comment #2" }).getByRole("listitem")).toHaveText([/Reply to Beta/]);
  await expect(page.getByRole("list", { name: "Replies to comment #1" })).toHaveCount(0);
  await expect(topLevel(page)).toHaveCount(2);
  await page.reload();
  await expect(page.getByRole("list", { name: "Replies to comment #2" }).getByRole("listitem")).toHaveText([/Reply to Beta/]);
});

test("edits are saved on the server", async ({ page }) => {
  await post(page, "Draft wording");
  await page.getByRole("button", { name: "Edit comment #1" }).click();
  await page.getByLabel("New text for comment #1").fill("Final wording");
  await page.getByRole("button", { name: "Save comment #1" }).click();
  await expect(thread(page)).toContainText("Final wording");
  await page.reload();
  await expect(thread(page)).toContainText("Final wording");
  await expect(thread(page)).not.toContainText("Draft wording");
});

test("delete needs confirmation and dismissing keeps the comment", async ({ page }) => {
  await post(page, "Keep me");
  page.once("dialog", (dialog) => dialog.dismiss());
  await page.getByRole("button", { name: "Delete comment #1" }).click();
  await expect(thread(page)).toContainText("Keep me");
  await page.reload();
  await expect(thread(page)).toContainText("Keep me");
  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "Delete comment #1" }).click();
  await expect(thread(page)).not.toContainText("Keep me");
  await expect(page.getByText("0 comments")).toBeVisible();
  await page.reload();
  await expect(topLevel(page)).toHaveCount(0);
});
