import { expect, test } from "@playwright/test";

test.beforeEach(async ({ request }) => {
  await request.post("/api/reset");
});

test("supports posting, replying, editing, deleting, and persistence", async ({ page }) => {
  await page.goto("/");

  await expect(page.locator("#cm-count")).toHaveText("0 comments");

  await page.getByLabel("Your comment").fill("First comment");
  await page.getByRole("button", { name: "Post" }).click();
  await expect(page.getByText("#1 First comment")).toBeVisible();

  await page.getByLabel("Your comment").fill("Second comment");
  await page.getByRole("button", { name: "Post" }).click();
  await expect(page.getByText("#2 Second comment")).toBeVisible();

  await page.getByRole("button", { name: "Reply to comment #1" }).click();
  await page.getByLabel("Your comment").fill("Reply to first");
  await page.getByRole("button", { name: "Post" }).click();

  await expect(page.locator("#cm-count")).toHaveText("3 comments");
  await expect(page.locator("#cm-thread > li.comment")).toHaveCount(2);
  await expect(page.locator('li.comment[data-id="1"] > ul.replies > li.comment[data-id="3"] .text')).toHaveText(
    "#3 Reply to first",
  );
  await expect(page.locator('li.comment[data-id="2"] > ul.replies > li.comment[data-id="3"]')).toHaveCount(0);
  await expect(page.locator('#cm-thread > li.comment[data-id="3"]')).toHaveCount(0);

  await page.getByRole("button", { name: "Edit comment #1" }).click();
  await page.getByLabel("New text for comment #1").fill("First comment edited");
  await page.getByRole("button", { name: "Save comment #1" }).click();
  await expect(page.getByText("#1 First comment edited")).toBeVisible();
  await expect(page.getByText("#1 First comment", { exact: true })).toHaveCount(0);

  page.once("dialog", async (dialog) => {
    expect(dialog.message()).toBe("Delete this comment?");
    await dialog.dismiss();
  });
  await page.getByRole("button", { name: "Delete comment #2" }).click();
  await expect(page.getByText("#2 Second comment")).toBeVisible();
  await expect(page.locator("#cm-count")).toHaveText("3 comments");

  page.once("dialog", async (dialog) => {
    expect(dialog.message()).toBe("Delete this comment?");
    await dialog.accept();
  });
  await page.getByRole("button", { name: "Delete comment #2" }).click();
  await expect(page.getByText("#2 Second comment")).toHaveCount(0);
  await expect(page.locator("#cm-count")).toHaveText("2 comments");

  await page.reload();
  await expect(page.locator("#cm-count")).toHaveText("2 comments");
  await expect(page.getByText("#1 First comment edited")).toBeVisible();
  await expect(page.locator('li.comment[data-id="1"] > ul.replies > li.comment[data-id="3"] .text')).toHaveText(
    "#3 Reply to first",
  );
  await expect(page.getByText("#2 Second comment")).toHaveCount(0);
});
