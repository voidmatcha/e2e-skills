import { expect, test } from "@playwright/test";

const card = (page, id) => page.locator("article.issue", { hasText: `#${id} ` });
const titles = (page) => page.locator("article.issue h2");

test.beforeEach(async ({ page, request }) => {
  const res = await request.post("/api/reset");
  expect(res.ok()).toBeTruthy();
  await page.goto("/");
  await expect(titles(page)).toHaveCount(5);
});

test("lists seeded issues with initial counts, ordered by priority", async ({ page }) => {
  await expect(page.getByRole("button", { name: "All (5)" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Mine (1)" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Unassigned (3)" })).toBeVisible();
  await expect(titles(page)).toHaveText([
    "#103 Crash on empty cart",
    "#101 Login page flickers",
    "#105 Slow search results",
    "#102 Add CSV export",
    "#104 Update onboarding copy",
  ]);
  await expect(card(page, 105).locator(".assignee")).toHaveText("Assigned to Ada");
  await expect(card(page, 102).locator(".assignee")).toHaveText("Assigned to Grace");
});

test("assign to me and unassign update the card and chip counts", async ({ page }) => {
  const issue = card(page, 101);
  await expect(issue.locator(".assignee")).toHaveText("Unassigned");

  await issue.getByRole("button", { name: "Assign to me" }).click();
  await expect(issue.locator(".assignee")).toHaveText("Assigned to Ada");
  await expect(issue.getByRole("button", { name: "Unassign" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Mine (2)" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Unassigned (2)" })).toBeVisible();
  await expect(page.getByRole("button", { name: "All (5)" })).toBeVisible();

  await issue.getByRole("button", { name: "Unassign" }).click();
  await expect(issue.locator(".assignee")).toHaveText("Unassigned");
  await expect(issue.getByRole("button", { name: "Assign to me" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Mine (1)" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Unassigned (3)" })).toBeVisible();
});

test("Mine and Unassigned chips filter the list", async ({ page }) => {
  await card(page, 101).getByRole("button", { name: "Assign to me" }).click();
  await expect(page.getByRole("button", { name: "Mine (2)" })).toBeVisible();

  await page.getByRole("button", { name: /^Mine/ }).click();
  await expect(titles(page)).toHaveText(["#101 Login page flickers", "#105 Slow search results"]);

  await page.getByRole("button", { name: /^Unassigned/ }).click();
  await expect(titles(page)).toHaveText(["#103 Crash on empty cart", "#104 Update onboarding copy"]);

  await page.getByRole("button", { name: /^All/ }).click();
  await expect(titles(page)).toHaveCount(5);
});

test("changing priority updates the badge and reorders the list", async ({ page }) => {
  const issue = card(page, 104);
  await expect(issue.locator(".priority")).toHaveText("Priority: low");

  await issue.getByRole("combobox").selectOption("high");
  await expect(issue.locator(".priority")).toHaveText("Priority: high");
  await expect(titles(page)).toHaveText([
    "#103 Crash on empty cart",
    "#104 Update onboarding copy",
    "#101 Login page flickers",
    "#105 Slow search results",
    "#102 Add CSV export",
  ]);

  await card(page, 103).getByRole("combobox").selectOption("low");
  await expect(card(page, 103).locator(".priority")).toHaveText("Priority: low");
  await expect(titles(page)).toHaveText([
    "#104 Update onboarding copy",
    "#101 Login page flickers",
    "#105 Slow search results",
    "#102 Add CSV export",
    "#103 Crash on empty cart",
  ]);
});

test("assignments and priorities survive a reload", async ({ page }) => {
  await card(page, 101).getByRole("button", { name: "Assign to me" }).click();
  await card(page, 105).getByRole("button", { name: "Unassign" }).click();
  await card(page, 104).getByRole("combobox").selectOption("high");
  await expect(card(page, 104).locator(".priority")).toHaveText("Priority: high");
  await expect(card(page, 105).locator(".assignee")).toHaveText("Unassigned");

  await page.reload();
  await expect(titles(page)).toHaveCount(5);
  await expect(card(page, 101).locator(".assignee")).toHaveText("Assigned to Ada");
  await expect(card(page, 105).locator(".assignee")).toHaveText("Unassigned");
  await expect(card(page, 104).locator(".priority")).toHaveText("Priority: high");
  await expect(card(page, 104).getByRole("combobox")).toHaveValue("high");
  await expect(titles(page).first()).toHaveText("#103 Crash on empty cart");
  await expect(titles(page).nth(1)).toHaveText("#104 Update onboarding copy");
  await expect(page.getByRole("button", { name: "Mine (1)" })).toBeVisible();
});
