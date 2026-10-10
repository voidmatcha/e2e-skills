import { expect, test } from "@playwright/test";

const entries = (page) => page.getByRole("list", { name: "Entries" }).getByRole("listitem");

async function open(page) {
  const loaded = page.waitForResponse(
    (r) => r.url().endsWith("/api/entries") && r.request().method() === "GET",
  );
  await page.goto("/");
  await loaded;
}

async function sign(page, name, message) {
  await page.getByLabel("Name").fill(name);
  await page.getByLabel("Message").fill(message);
  const saved = page.waitForResponse(
    (r) => r.url().endsWith("/api/entries") && r.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Sign" }).click();
  await saved;
}

test.beforeEach(async ({ request }) => {
  const res = await request.post("/api/reset");
  expect(res.ok()).toBeTruthy();
});

test("submitting name and message adds the entry to the list", async ({ page }) => {
  await open(page);
  await sign(page, "Ada", "Hello there");

  await expect(entries(page)).toHaveCount(1);
  await expect(entries(page).first()).toContainText("Ada");
  await expect(entries(page).first()).toContainText("Hello there");
  await expect(page.getByLabel("Name")).toHaveValue("");
  await expect(page.getByLabel("Message")).toHaveValue("");
});

test("lists entries newest first", async ({ page }) => {
  await open(page);
  await sign(page, "First", "one");
  await expect(entries(page)).toHaveCount(1);
  await sign(page, "Second", "two");
  await expect(entries(page)).toHaveCount(2);
  await sign(page, "Third", "three");
  await expect(entries(page)).toHaveCount(3);

  await expect(entries(page).nth(0)).toContainText("Third");
  await expect(entries(page).nth(1)).toContainText("Second");
  await expect(entries(page).nth(2)).toContainText("First");

  // Order is the same after a reload from server state.
  await open(page);
  await expect(entries(page).nth(0)).toContainText("Third");
  await expect(entries(page).nth(2)).toContainText("First");
});

test("counter shows the number of entries", async ({ page }) => {
  const counter = page.locator("#gb-count");
  await open(page);
  await expect(counter).toHaveText("0 entries");

  await sign(page, "A", "one");
  await expect(counter).toHaveText("1 entry");

  await sign(page, "B", "two");
  await expect(counter).toHaveText("2 entries");

  await sign(page, "C", "three");
  await expect(counter).toHaveText("3 entries");
});

test("entries are stored on the server", async ({ page, request }) => {
  await open(page);
  await sign(page, "Grace", "Persisted");

  const res = await request.get("/api/entries");
  expect(res.ok()).toBeTruthy();
  expect(await res.json()).toEqual([
    expect.objectContaining({ name: "Grace", message: "Persisted" }),
  ]);

  await open(page);
  await expect(entries(page)).toHaveCount(1);
  await expect(entries(page).first()).toContainText("Grace");
  await expect(entries(page).first()).toContainText("Persisted");
  await expect(page.locator("#gb-count")).toHaveText("1 entry");
});

test("an empty message shows an error and adds nothing", async ({ page, request }) => {
  await open(page);
  await page.getByLabel("Name").fill("Linus");
  const rejected = page.waitForResponse(
    (r) => r.url().endsWith("/api/entries") && r.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Sign" }).click();
  expect((await rejected).status()).toBe(400);

  await expect(page.getByRole("alert")).toHaveText("Message is required");
  await expect(entries(page)).toHaveCount(0);
  await expect(page.locator("#gb-count")).toHaveText("0 entries");
  expect(await (await request.get("/api/entries")).json()).toEqual([]);
});

test("the error disappears after a later successful submission", async ({ page }) => {
  await open(page);
  await page.getByLabel("Name").fill("Linus");
  const rejected = page.waitForResponse(
    (r) => r.url().endsWith("/api/entries") && r.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Sign" }).click();
  await rejected;
  await expect(page.getByRole("alert")).toHaveText("Message is required");

  await sign(page, "Linus", "Now with a message");

  await expect(entries(page)).toHaveCount(1);
  await expect(page.getByRole("alert")).toHaveText("");
  await expect(page.getByText("Message is required")).toHaveCount(0);
});
