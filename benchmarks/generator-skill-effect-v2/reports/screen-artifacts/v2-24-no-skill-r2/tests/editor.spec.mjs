import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page, request }) => {
  await request.post("/api/reset");
  // The editor fills itself from /api/state after load; wait so typing is not overwritten.
  const loaded = page.waitForResponse("**/api/state");
  await page.goto("/");
  await loaded;
});

const title = (page) => page.getByLabel("Title");
const body = (page) => page.getByLabel("Body");
const status = (page) => page.getByRole("status");

async function reload(page) {
  const loaded = page.waitForResponse("**/api/state");
  await page.reload();
  await loaded;
}

test("autosaves the draft and restores title and body after reload", async ({ page }) => {
  await title(page).fill("My title");
  await body(page).fill("First line\nSecond line  ");
  await expect(status(page)).toHaveText("Draft saved");

  await reload(page);
  await expect(title(page)).toHaveValue("My title");
  await expect(body(page)).toHaveValue("First line\nSecond line  ");
});

test("restores the text as last typed after several edits", async ({ page }) => {
  await title(page).pressSequentially("Hello wxx");
  await body(page).pressSequentially("abc");
  await title(page).press("End");
  await title(page).press("Backspace");
  await title(page).press("Backspace");
  await title(page).pressSequentially("orld");
  await body(page).pressSequentially("def");
  await expect(status(page)).toHaveText("Draft saved");

  await reload(page);
  await expect(title(page)).toHaveValue("Hello world");
  await expect(body(page)).toHaveValue("abcdef");
});

test("publish adds the post, empties the editor and clears the stored draft", async ({ page }) => {
  await title(page).fill("Published title");
  await body(page).fill("Published body");
  await expect(status(page)).toHaveText("Draft saved");

  await page.getByRole("button", { name: "Publish" }).click();
  await expect(page.getByRole("list", { name: "Published posts" }).getByRole("listitem")).toHaveText(["Published title"]);
  await expect(title(page)).toHaveValue("");
  await expect(body(page)).toHaveValue("");

  await reload(page);
  await expect(title(page)).toHaveValue("");
  await expect(body(page)).toHaveValue("");
  await expect(page.getByRole("list", { name: "Published posts" }).getByRole("listitem")).toHaveText(["Published title"]);
});

test("publish right after typing does not resurrect the draft", async ({ page }) => {
  await title(page).fill("Quick post");
  await body(page).fill("Quick body");
  await page.getByRole("button", { name: "Publish" }).click();
  await expect(status(page)).toHaveText("Published");

  // Outlast the autosave debounce, then reload.
  await page.waitForTimeout(600);
  await reload(page);
  await expect(title(page)).toHaveValue("");
  await expect(body(page)).toHaveValue("");
});

test("discard draft empties the editor and clears the stored draft", async ({ page }) => {
  await title(page).fill("Throwaway");
  await body(page).fill("Throwaway body");
  await expect(status(page)).toHaveText("Draft saved");

  await page.getByRole("button", { name: "Discard draft" }).click();
  await expect(title(page)).toHaveValue("");
  await expect(body(page)).toHaveValue("");

  await reload(page);
  await expect(title(page)).toHaveValue("");
  await expect(body(page)).toHaveValue("");
  await expect(page.getByRole("list", { name: "Published posts" }).getByRole("listitem")).toHaveCount(0);
});

test("discard right after typing does not resurrect the draft", async ({ page }) => {
  await title(page).fill("Gone");
  await page.getByRole("button", { name: "Discard draft" }).click();
  await page.waitForTimeout(600);

  await reload(page);
  await expect(title(page)).toHaveValue("");
  await expect(body(page)).toHaveValue("");
});
