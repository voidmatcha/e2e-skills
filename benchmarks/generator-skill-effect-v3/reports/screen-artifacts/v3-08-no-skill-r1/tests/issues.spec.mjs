import { expect, test } from "@playwright/test";

const card = (page, id) => page.locator("article").filter({ has: page.getByRole("heading", { name: new RegExp(`^#${id} `) }) });
const titles = async (page) => (await page.locator("article h2").allTextContents()).map((t) => t.split(" ")[0]);

test.beforeEach(async ({ page, request }) => {
  const res = await request.post("/api/reset");
  expect(res.ok()).toBeTruthy();
  await page.goto("/");
  await expect(page.locator("article")).toHaveCount(5);
});

test("filter chips show live counts", async ({ page }) => {
  await expect(page.getByRole("button", { name: "All (5)" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Mine (1)" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Unassigned (3)" })).toBeVisible();
});

test("seeded assignees are shown", async ({ page }) => {
  await expect(card(page, 105).locator(".assignee")).toHaveText("Assigned to Ada");
  await expect(card(page, 102).locator(".assignee")).toHaveText("Assigned to Grace");
  await expect(card(page, 101).locator(".assignee")).toHaveText("Unassigned");
});

test("Assign to me then Unassign toggles the assignee", async ({ page }) => {
  const issue = card(page, 101);
  await issue.getByRole("button", { name: "Assign to me" }).click();
  await expect(issue.locator(".assignee")).toHaveText("Assigned to Ada");
  await expect(issue.getByRole("button", { name: "Unassign" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Mine (2)" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Unassigned (2)" })).toBeVisible();

  await issue.getByRole("button", { name: "Unassign" }).click();
  await expect(issue.locator(".assignee")).toHaveText("Unassigned");
  await expect(issue.getByRole("button", { name: "Assign to me" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Mine (1)" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Unassigned (3)" })).toBeVisible();
});

test("Mine chip shows only Ada's issues", async ({ page }) => {
  await page.getByRole("button", { name: "Mine (1)" }).click();
  await expect(page.locator("article")).toHaveCount(1);
  await expect(card(page, 105)).toBeVisible();
  await expect(card(page, 102)).toHaveCount(0);
});

test("Mine filter includes a newly assigned issue", async ({ page }) => {
  await card(page, 103).getByRole("button", { name: "Assign to me" }).click();
  await page.getByRole("button", { name: "Mine (2)" }).click();
  await expect(page.locator("article")).toHaveCount(2);
  expect(await titles(page)).toEqual(["#103", "#105"]);
});

test("changing priority updates the badge and ordering", async ({ page }) => {
  // seed order: high 103, medium 101 105, low 102 104
  expect(await titles(page)).toEqual(["#103", "#101", "#105", "#102", "#104"]);

  await card(page, 104).getByRole("combobox").selectOption("high");
  await expect(card(page, 104).locator(".priority")).toHaveText("Priority: high");
  expect(await titles(page)).toEqual(["#103", "#104", "#101", "#105", "#102"]);

  await card(page, 103).getByRole("combobox").selectOption("low");
  await expect(card(page, 103).locator(".priority")).toHaveText("Priority: low");
  expect(await titles(page)).toEqual(["#104", "#101", "#105", "#102", "#103"]);
});

test("assignments and priorities survive a reload", async ({ page }) => {
  await card(page, 101).getByRole("button", { name: "Assign to me" }).click();
  await expect(card(page, 101).locator(".assignee")).toHaveText("Assigned to Ada");
  await card(page, 105).getByRole("button", { name: "Unassign" }).click();
  await expect(card(page, 105).locator(".assignee")).toHaveText("Unassigned");
  await card(page, 102).getByRole("combobox").selectOption("high");
  await expect(card(page, 102).locator(".priority")).toHaveText("Priority: high");

  await page.reload();
  await expect(page.locator("article")).toHaveCount(5);
  await expect(card(page, 101).locator(".assignee")).toHaveText("Assigned to Ada");
  await expect(card(page, 105).locator(".assignee")).toHaveText("Unassigned");
  await expect(card(page, 102).locator(".priority")).toHaveText("Priority: high");
  await expect(card(page, 102).getByRole("combobox")).toHaveValue("high");
  expect(await titles(page)).toEqual(["#102", "#103", "#101", "#105", "#104"]);
});
