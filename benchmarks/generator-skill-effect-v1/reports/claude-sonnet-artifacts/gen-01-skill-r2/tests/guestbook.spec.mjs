import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page, request }) => {
  // /api/reset is the app's test seam: every test starts from an empty guestbook.
  const reset = await request.post("/api/reset");
  expect(reset.ok()).toBe(true);

  // The page replaces its state with the stored list once this fetch settles,
  // so wait for it before interacting.
  const loaded = page.waitForResponse(
    (r) => r.url().endsWith("/api/entries") && r.request().method() === "GET",
  );
  await page.goto("/");
  await loaded;
});

const nameInput = (page) => page.getByLabel("Name");
const messageInput = (page) => page.getByLabel("Message");
const entries = (page) => page.getByRole("list", { name: "Entries" }).getByRole("listitem");
const counter = (page) => page.locator("#gb-count");
const error = (page) => page.getByRole("alert");

// Fills and submits the form, then waits for the POST /api/entries response.
async function sign(page, name, message) {
  await nameInput(page).fill(name);
  await messageInput(page).fill(message);
  const posted = page.waitForResponse(
    (r) => r.url().endsWith("/api/entries") && r.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Sign" }).click();
  return posted;
}

test("adds a submitted entry to the list with its name and message", async ({ page }) => {
  const response = await sign(page, "Alice", "Hello there");
  expect(response.status()).toBe(201);
  expect(response.request().postDataJSON()).toEqual({ name: "Alice", message: "Hello there" });

  await expect(entries(page)).toHaveText(["Alice Hello there"]);
});

test("lists entries newest first", async ({ page }) => {
  await sign(page, "Alice", "first");
  await expect(entries(page)).toHaveCount(1);
  await sign(page, "Bob", "second");

  await expect(entries(page)).toHaveText(["Bob second", "Alice first"]);
});

test("shows 1 entry in the counter after one submission", async ({ page }) => {
  await sign(page, "Alice", "first");

  await expect(counter(page)).toHaveText("1 entry");
});

test("shows N entries in the counter after several submissions", async ({ page }) => {
  await sign(page, "Alice", "first");
  await expect(entries(page)).toHaveCount(1);
  await sign(page, "Bob", "second");

  await expect(counter(page)).toHaveText("2 entries");
});

test("keeps entries on the server across a reload", async ({ page, request }) => {
  await sign(page, "Alice", "Hello there");
  await expect(entries(page)).toHaveCount(1);

  const stored = await request.get("/api/entries");
  expect(await stored.json()).toEqual([expect.objectContaining({ name: "Alice", message: "Hello there" })]);

  await page.reload();
  await expect(entries(page)).toHaveText(["Alice Hello there"]);
});

test("rejects an empty message with an error and stores nothing", async ({ page, request }) => {
  const response = await sign(page, "Alice", "");
  expect(response.status()).toBe(400);

  await expect(error(page)).toHaveText("Message is required");

  // Re-read from the server: the rejected write must not have stored anything.
  const stored = await request.get("/api/entries");
  expect(await stored.json()).toEqual([]);
  await page.reload();
  await expect(entries(page)).toHaveCount(0);
  await expect(counter(page)).toHaveText("0 entries");
});

test("clears the error after a later successful submission", async ({ page }) => {
  await sign(page, "Alice", "");
  await expect(error(page)).toHaveText("Message is required");

  const response = await sign(page, "Alice", "Hello there");
  expect(response.status()).toBe(201);

  await expect(error(page)).toHaveText("");
  await expect(entries(page)).toHaveText(["Alice Hello there"]);
});
