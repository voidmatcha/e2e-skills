import { expect, test } from "@playwright/test";

// Entries live in server memory, so every test starts from a reset server.
test.beforeEach(async ({ page, request }) => {
  const reset = await request.post("/api/reset");
  expect(reset.ok()).toBe(true);
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Guestbook" })).toBeVisible();
});

// The counter has no role or testid; its id is the only stable hook.
const counter = (page) => page.locator("#gb-count");

async function sign(page, name, message) {
  await page.getByLabel("Name").fill(name);
  await page.getByLabel("Message").fill(message);
  const saved = page.waitForResponse(
    (res) => res.url().endsWith("/api/entries") && res.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Sign" }).click();
  const res = await saved;
  // The page re-enables and clears the message field once it has handled the response.
  await expect(page.getByLabel("Message")).toBeEnabled();
  await expect(page.getByLabel("Message")).toHaveValue("");
  return res;
}

test("a signed entry appears in the list with its name and message", async ({ page }) => {
  const res = await sign(page, "Alice", "Hello there");
  expect(res.status()).toBe(201);

  const entries = page.getByRole("list", { name: "Entries" }).getByRole("listitem");
  await expect(entries).toHaveCount(1);
  await expect(entries.first()).toContainText("Alice");
  await expect(entries.first()).toContainText("Hello there");
});

test("entries are listed newest first", async ({ page }) => {
  await sign(page, "Alice", "first");
  await sign(page, "Bob", "second");
  await sign(page, "Carol", "third");

  const entries = page.getByRole("list", { name: "Entries" }).getByRole("listitem");
  const newestFirst = ["Carol third", "Bob second", "Alice first"];
  await expect(entries).toHaveText(newestFirst);

  // The server's own order must match, not just the page's local state.
  await page.reload();
  await expect(entries).toHaveText(newestFirst);
});

test("the counter shows 0 entries, 1 entry, then N entries", async ({ page }) => {
  await expect(counter(page)).toHaveText("0 entries");

  await sign(page, "Alice", "first");
  await expect(counter(page)).toHaveText("1 entry");

  await sign(page, "Bob", "second");
  await expect(counter(page)).toHaveText("2 entries");
});

test("entries are stored on the server and survive a reload", async ({ page, request }) => {
  await sign(page, "Alice", "Stored remotely");

  const stored = await request.get("/api/entries");
  expect(await stored.json()).toEqual([
    expect.objectContaining({ name: "Alice", message: "Stored remotely" }),
  ]);

  await page.reload();
  const entries = page.getByRole("list", { name: "Entries" }).getByRole("listitem");
  await expect(entries).toHaveText(["Alice Stored remotely"]);
  await expect(counter(page)).toHaveText("1 entry");
});

test("an empty message shows an error and adds nothing", async ({ page, request }) => {
  const res = await sign(page, "Alice", "");
  expect(res.status()).toBe(400);

  await expect(page.getByRole("alert")).toHaveText("Message is required");
  await expect(counter(page)).toHaveText("0 entries");
  await expect(page.getByRole("listitem")).toHaveCount(0);

  // Re-read after the rejected write: nothing may have been stored.
  expect(await (await request.get("/api/entries")).json()).toEqual([]);
  await page.reload();
  await expect(counter(page)).toHaveText("0 entries");
  await expect(page.getByRole("listitem")).toHaveCount(0);
});

test("the error disappears after a later successful submission", async ({ page }) => {
  await sign(page, "Alice", "");
  await expect(page.getByRole("alert")).toHaveText("Message is required");

  const res = await sign(page, "Alice", "Now with a message");
  expect(res.status()).toBe(201);

  await expect(page.getByRole("listitem")).toHaveText(["Alice Now with a message"]);
  await expect(page.getByRole("alert")).toBeEmpty();
});
