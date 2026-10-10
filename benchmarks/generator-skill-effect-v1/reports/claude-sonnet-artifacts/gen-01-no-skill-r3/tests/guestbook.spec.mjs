import { expect, test } from "@playwright/test";

async function open(page) {
  const loaded = page.waitForResponse((r) => r.url().endsWith("/api/entries") && r.request().method() === "GET");
  await page.goto("/");
  await loaded;
}

async function sign(page, name, message) {
  await page.getByLabel("Name").fill(name);
  await page.getByLabel("Message").fill(message);
  await page.getByRole("button", { name: "Sign" }).click();
}

test.beforeEach(async ({ request }) => {
  const res = await request.post("/api/reset");
  expect(res.ok()).toBeTruthy();
});

test("a submitted entry appears with its name and message", async ({ page }) => {
  await open(page);
  await sign(page, "Ada", "Hello there");
  const items = page.getByRole("list", { name: "Entries" }).getByRole("listitem");
  await expect(items).toHaveCount(1);
  await expect(items.first()).toContainText("Ada");
  await expect(items.first()).toContainText("Hello there");
  await expect(page.getByLabel("Name")).toHaveValue("");
  await expect(page.getByLabel("Message")).toHaveValue("");
});

test("entries are listed newest first", async ({ page }) => {
  await open(page);
  await sign(page, "First", "one");
  await expect(page.getByRole("listitem")).toHaveCount(1);
  await sign(page, "Second", "two");
  await expect(page.getByRole("listitem")).toHaveCount(2);
  await sign(page, "Third", "three");
  const items = page.getByRole("listitem");
  await expect(items).toHaveCount(3);
  await expect(items.nth(0)).toContainText("Third");
  await expect(items.nth(1)).toContainText("Second");
  await expect(items.nth(2)).toContainText("First");
});

test("the counter shows the number of entries", async ({ page }) => {
  await open(page);
  const counter = page.locator("#gb-count");
  await expect(counter).toHaveText("0 entries");
  await sign(page, "A", "one");
  await expect(counter).toHaveText("1 entry");
  await sign(page, "B", "two");
  await expect(counter).toHaveText("2 entries");
});

test("entries are stored on the server and survive a reload", async ({ page, request }) => {
  await open(page);
  await sign(page, "Grace", "Persist me");
  await expect(page.getByRole("listitem")).toHaveCount(1);

  const stored = await (await request.get("/api/entries")).json();
  expect(stored).toHaveLength(1);
  expect(stored[0]).toMatchObject({ name: "Grace", message: "Persist me" });

  await open(page);
  const items = page.getByRole("listitem");
  await expect(items).toHaveCount(1);
  await expect(items.first()).toContainText("Grace");
  await expect(items.first()).toContainText("Persist me");
  await expect(page.locator("#gb-count")).toHaveText("1 entry");
});

test("an empty message shows an error and adds nothing", async ({ page, request }) => {
  await open(page);
  await sign(page, "Ada", "");
  await expect(page.getByRole("alert")).toHaveText("Message is required");
  await expect(page.getByRole("listitem")).toHaveCount(0);
  await expect(page.locator("#gb-count")).toHaveText("0 entries");
  expect(await (await request.get("/api/entries")).json()).toEqual([]);
});

test("the error disappears after a later successful submission", async ({ page }) => {
  await open(page);
  await sign(page, "Ada", "");
  await expect(page.getByRole("alert")).toHaveText("Message is required");
  await sign(page, "Ada", "Now with a message");
  await expect(page.getByRole("listitem")).toHaveCount(1);
  await expect(page.getByRole("alert")).toHaveText("");
});
