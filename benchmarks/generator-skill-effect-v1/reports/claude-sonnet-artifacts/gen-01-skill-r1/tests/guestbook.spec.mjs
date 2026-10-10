import { expect, test } from "@playwright/test";

test.describe("guestbook", () => {
  test.beforeEach(async ({ page, request }) => {
    // Entries live in server memory, so every test starts from a cleared server.
    const reset = await request.post("/api/reset");
    expect(reset.ok()).toBe(true);

    // The page renders "0 entries" before its initial GET /api/entries lands, and that
    // response replaces the page state; wait for it so a fast submit is not overwritten.
    const initialLoad = page.waitForResponse(
      (res) => res.url().endsWith("/api/entries") && res.request().method() === "GET",
    );
    await page.goto("/");
    await initialLoad;
  });

  const sign = async (page, name, message) => {
    await page.getByLabel("Name", { exact: true }).fill(name);
    await page.getByLabel("Message", { exact: true }).fill(message);
    await page.getByRole("button", { name: "Sign" }).click();
  };

  test("adds a signed entry showing the name and the message", async ({ page }) => {
    const created = page.waitForRequest(
      (req) => req.url().endsWith("/api/entries") && req.method() === "POST",
    );
    await sign(page, "Alice", "Hello there");
    expect((await created).postDataJSON()).toEqual({ name: "Alice", message: "Hello there" });

    await expect(page.getByRole("list", { name: "Entries" }).getByRole("listitem")).toHaveText([
      "Alice Hello there",
    ]);
  });

  test("lists entries newest first", async ({ page }) => {
    const entries = page.getByRole("list", { name: "Entries" }).getByRole("listitem");

    await sign(page, "Alice", "first");
    await expect(entries).toHaveText(["Alice first"]);
    await sign(page, "Bob", "second");

    await expect(entries).toHaveText(["Bob second", "Alice first"]);
  });

  test("counts entries as 1 entry, then N entries", async ({ page }) => {
    const counter = page.getByText(/^\d+ entr(y|ies)$/);
    await expect(counter).toHaveText("0 entries");

    await sign(page, "Alice", "first");
    await expect(counter).toHaveText("1 entry");

    await sign(page, "Bob", "second");
    await expect(counter).toHaveText("2 entries");
  });

  test("keeps entries on the server across a reload", async ({ page, request }) => {
    await sign(page, "Alice", "Still here");
    const entries = page.getByRole("list", { name: "Entries" }).getByRole("listitem");
    await expect(entries).toHaveText(["Alice Still here"]);

    const initialLoad = page.waitForResponse(
      (res) => res.url().endsWith("/api/entries") && res.request().method() === "GET",
    );
    await page.reload();
    await initialLoad;

    await expect(entries).toHaveText(["Alice Still here"]);
    const stored = await (await request.get("/api/entries")).json();
    expect(stored).toMatchObject([{ name: "Alice", message: "Still here" }]);
  });

  test("rejects an empty message with an error and adds nothing", async ({ page, request }) => {
    const rejected = page.waitForResponse(
      (res) => res.url().endsWith("/api/entries") && res.request().method() === "POST",
    );
    await page.getByLabel("Name", { exact: true }).fill("Alice");
    await page.getByRole("button", { name: "Sign" }).click();
    expect((await rejected).status()).toBe(400);

    await expect(page.getByRole("alert")).toHaveText("Message is required");

    // Re-read stored state: the failed submit never refreshes the list on its own.
    const initialLoad = page.waitForResponse(
      (res) => res.url().endsWith("/api/entries") && res.request().method() === "GET",
    );
    await page.reload();
    await initialLoad;
    await expect(page.getByRole("list", { name: "Entries" }).getByRole("listitem")).toHaveCount(0);
    await expect(page.getByText(/^\d+ entr(y|ies)$/)).toHaveText("0 entries");
    expect(await (await request.get("/api/entries")).json()).toEqual([]);
  });

  test("clears the error after a later successful submission", async ({ page }) => {
    const alert = page.getByRole("alert");
    await page.getByLabel("Name", { exact: true }).fill("Alice");
    await page.getByRole("button", { name: "Sign" }).click();
    await expect(alert).toHaveText("Message is required");

    await sign(page, "Alice", "Now with a message");
    await expect(page.getByRole("list", { name: "Entries" }).getByRole("listitem")).toHaveText([
      "Alice Now with a message",
    ]);

    await expect(alert).toHaveText("");
  });
});
