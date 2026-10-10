import { expect, test } from "@playwright/test";

const title = (page) => page.getByLabel("Title");
const body = (page) => page.getByLabel("Body");
const status = (page) => page.getByRole("status");
const posts = (page) => page.getByRole("list", { name: "Published posts" }).getByRole("listitem");

test.beforeEach(async ({ page }) => {
  await page.request.post("/api/reset");
  await page.goto("/");
  await expect(title(page)).toHaveValue("");
});

test("typing saves the draft exactly as typed and a reload restores it", async ({ page }) => {
  await title(page).pressSequentially("Autumn notes", { delay: 20 });
  await body(page).pressSequentially("First line of the post.", { delay: 20 });
  await expect(status(page)).toHaveText("Draft saved");
  await page.reload();
  await expect(title(page)).toHaveValue("Autumn notes");
  await expect(body(page)).toHaveValue("First line of the post.");
});

test("publish lists the post and clears the stored draft", async ({ page }) => {
  await title(page).fill("Hello world");
  await body(page).fill("Body text");
  await expect(status(page)).toHaveText("Draft saved");
  await page.getByRole("button", { name: "Publish" }).click();
  await expect(posts(page)).toHaveText(["Hello world"]);
  await expect(title(page)).toHaveValue("");
  await expect(body(page)).toHaveValue("");
  await page.reload();
  await expect(posts(page)).toHaveText(["Hello world"]);
  await expect(title(page)).toHaveValue("");
  await expect(body(page)).toHaveValue("");
});

test("discard clears the editor and the stored draft", async ({ page }) => {
  await title(page).fill("Throwaway");
  await body(page).fill("Nothing to see");
  await expect(status(page)).toHaveText("Draft saved");
  await page.getByRole("button", { name: "Discard draft" }).click();
  await expect(title(page)).toHaveValue("");
  await expect(body(page)).toHaveValue("");
  await page.reload();
  await expect(title(page)).toHaveValue("");
  await expect(body(page)).toHaveValue("");
});
