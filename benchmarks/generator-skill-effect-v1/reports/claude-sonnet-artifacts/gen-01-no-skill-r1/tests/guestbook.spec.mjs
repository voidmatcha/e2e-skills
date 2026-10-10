import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page, request }) => {
  const res = await request.post("/api/reset");
  expect(res.ok()).toBeTruthy();
  await page.goto("/");
});

async function sign(page, name, message) {
  await page.getByLabel("Name").fill(name);
  await page.getByLabel("Message").fill(message);
  await page.getByRole("button", { name: "Sign" }).click();
}

const entries = (page) => page.getByRole("list", { name: "Entries" }).getByRole("listitem");

test("adds a submitted entry showing name and message", async ({ page }) => {
  await sign(page, "Ada", "Hello there");
  await expect(entries(page)).toHaveCount(1);
  await expect(entries(page).first()).toContainText("Ada");
  await expect(entries(page).first()).toContainText("Hello there");
  await expect(page.getByLabel("Message")).toHaveValue("");
});

test("lists entries newest first", async ({ page }) => {
  await sign(page, "First", "one");
  await expect(entries(page)).toHaveCount(1);
  await sign(page, "Second", "two");
  await expect(entries(page)).toHaveCount(2);
  await sign(page, "Third", "three");
  await expect(entries(page)).toHaveCount(3);
  await expect(entries(page).nth(0)).toContainText("Third");
  await expect(entries(page).nth(1)).toContainText("Second");
  await expect(entries(page).nth(2)).toContainText("First");
});

test("counter shows singular and plural forms", async ({ page }) => {
  const count = page.locator("#gb-count");
  await expect(count).toHaveText("0 entries");
  await sign(page, "A", "one");
  await expect(count).toHaveText("1 entry");
  await sign(page, "B", "two");
  await expect(count).toHaveText("2 entries");
});

test("entries are stored on the server and survive reload", async ({ page, request }) => {
  await sign(page, "Grace", "Persisted");
  await expect(entries(page)).toHaveCount(1);

  const res = await request.get("/api/entries");
  const body = await res.json();
  expect(body).toHaveLength(1);
  expect(body[0]).toMatchObject({ name: "Grace", message: "Persisted" });

  await page.reload();
  await expect(entries(page)).toHaveCount(1);
  await expect(entries(page).first()).toContainText("Grace");
  await expect(entries(page).first()).toContainText("Persisted");
  await expect(page.locator("#gb-count")).toHaveText("1 entry");
});

test("empty message shows an error and adds nothing", async ({ page, request }) => {
  await sign(page, "Ada", "");
  await expect(page.getByRole("alert")).toHaveText("Message is required");
  await expect(entries(page)).toHaveCount(0);
  await expect(page.locator("#gb-count")).toHaveText("0 entries");
  const body = await (await request.get("/api/entries")).json();
  expect(body).toEqual([]);
});

test("error disappears after a later successful submission", async ({ page }) => {
  await sign(page, "Ada", "");
  await expect(page.getByRole("alert")).toHaveText("Message is required");
  await sign(page, "Ada", "Now with a message");
  await expect(entries(page)).toHaveCount(1);
  await expect(page.getByRole("alert")).toHaveText("");
});
