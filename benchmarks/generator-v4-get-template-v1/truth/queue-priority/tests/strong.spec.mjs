import { expect, test } from "@playwright/test";

test.beforeEach(async ({ request }) => {
  expect((await request.post("/api/reset")).ok()).toBe(true);
});

test.afterEach(async ({ request }) => {
  expect((await request.post("/api/reset")).ok()).toBe(true);
});

test("promotes exactly one item and persists the priority order", async ({ page }) => {
  const writes = [];
  page.on("request", (request) => {
    const url = new URL(request.url());
    if (url.pathname === "/api/promote") {
      writes.push([request.method(), url.searchParams.get("item")]);
    }
  });

  await page.goto("/");
  const status = page.getByRole("status");
  const order = page.getByRole("list", { name: "Priority order" }).getByRole("listitem");
  await expect(status).toHaveText("First: Raven");
  await expect(order).toHaveText(["Raven", "Finch"]);

  await page.getByRole("button", { name: "Promote Finch" }).click();
  await expect(status).toHaveText("First: Finch");
  await expect(order).toHaveText(["Finch", "Raven"]);

  await page.reload();
  await expect(status).toHaveText("First: Finch");
  await expect(order).toHaveText(["Finch", "Raven"]);

  await page.getByRole("button", { name: "Promote Raven" }).click();
  await expect(status).toHaveText("First: Raven");
  await expect(order).toHaveText(["Raven", "Finch"]);

  await page.getByRole("button", { name: "Promote Finch" }).click();
  await expect(status).toHaveText("First: Finch");
  await expect(order).toHaveText(["Finch", "Raven"]);
  expect(writes).toEqual([["GET", "finch"], ["GET", "raven"], ["GET", "finch"]]);
});
