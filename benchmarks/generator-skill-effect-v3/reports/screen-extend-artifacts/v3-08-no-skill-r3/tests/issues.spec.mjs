import { expect, test } from "@playwright/test";

const card = (page, id) => page.locator("article.issue").filter({ hasText: `#${id} ` });
const order = async (page) =>
  (await page.locator("article.issue h2").allTextContents()).map((t) => Number(t.match(/#(\d+)/)[1]));

test.beforeEach(async ({ page, request }) => {
  await request.post("/api/reset");
  await page.goto("/");
  await expect(page.locator("article.issue")).toHaveCount(5);
});

test("filter chips show live counts", async ({ page }) => {
  await expect(page.getByRole("button", { name: "All (5)" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Mine (1)" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Unassigned (3)" })).toBeVisible();
});

test("Mine chip shows only Ada's issues", async ({ page }) => {
  await page.getByRole("button", { name: "Mine (1)" }).click();
  await expect(page.locator("article.issue")).toHaveCount(1);
  await expect(page.locator("article.issue h2")).toHaveText("#105 Slow search results");
});

test("assign and unassign update the line, button and counts", async ({ page }) => {
  const c = card(page, 101);
  await expect(c.locator(".assignee")).toHaveText("Unassigned");
  await c.getByRole("button", { name: "Assign to me" }).click();
  await expect(c.locator(".assignee")).toHaveText("Assigned to Ada");
  await expect(c.getByRole("button", { name: "Unassign" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Mine (2)" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Unassigned (2)" })).toBeVisible();

  await c.getByRole("button", { name: "Unassign" }).click();
  await expect(c.locator(".assignee")).toHaveText("Unassigned");
  await expect(c.getByRole("button", { name: "Assign to me" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Mine (1)" })).toBeVisible();
});

test("assignment survives a reload", async ({ page }) => {
  const c = card(page, 103);
  await c.getByRole("button", { name: "Assign to me" }).click();
  await expect(c.locator(".assignee")).toHaveText("Assigned to Ada");
  await page.reload();
  await expect(card(page, 103).locator(".assignee")).toHaveText("Assigned to Ada");
  await expect(page.getByRole("button", { name: "Mine (2)" })).toBeVisible();
});

test("priority change updates the badge, ordering and survives reload", async ({ page }) => {
  expect(await order(page)).toEqual([103, 101, 105, 102, 104]);

  await card(page, 104).getByRole("combobox").selectOption("high");
  await expect(card(page, 104).locator(".priority")).toHaveText("Priority: high");
  expect(await order(page)).toEqual([103, 104, 101, 105, 102]);

  await card(page, 103).getByRole("combobox").selectOption("low");
  await expect(card(page, 103).locator(".priority")).toHaveText("Priority: low");
  expect(await order(page)).toEqual([104, 101, 105, 102, 103]);

  await page.reload();
  await expect(page.locator("article.issue")).toHaveCount(5);
  await expect(card(page, 104).locator(".priority")).toHaveText("Priority: high");
  await expect(card(page, 103).locator(".priority")).toHaveText("Priority: low");
  expect(await order(page)).toEqual([104, 101, 105, 102, 103]);
});
