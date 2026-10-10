import { expect, test } from "@playwright/test";

const issue = (page, id) => page.locator("article").filter({ hasText: `#${id} ` });
const titles = (page) => page.locator("article h2").allTextContents();

test.beforeEach(async ({ request }) => {
  await request.post("/api/reset");
});

test("shows live filter counts and filters Ada's issues", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByRole("button", { name: "All (5)" })).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByRole("button", { name: "Mine (1)" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Unassigned (3)" })).toBeVisible();

  await issue(page, 101).getByRole("button", { name: "Assign to me: Login page flickers" }).click();

  await expect(page.getByRole("button", { name: "All (5)" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Mine (2)" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Unassigned (2)" })).toBeVisible();

  await page.getByRole("button", { name: "Mine (2)" }).click();

  await expect(page.getByRole("button", { name: "Mine (2)" })).toHaveAttribute("aria-pressed", "true");
  await expect(issue(page, 101)).toBeVisible();
  await expect(issue(page, 105)).toBeVisible();
  await expect(page.locator("article")).toHaveCount(2);
});

test("assigning and unassigning an issue updates the row and survives reload", async ({ page }) => {
  await page.goto("/");

  await expect(issue(page, 101).locator(".assignee")).toHaveText("Unassigned");
  await issue(page, 101).getByRole("button", { name: "Assign to me: Login page flickers" }).click();

  await expect(issue(page, 101).locator(".assignee")).toHaveText("Assigned to Ada");
  await expect(issue(page, 101).getByRole("button", { name: "Unassign Login page flickers" })).toBeVisible();

  await page.reload();

  await expect(issue(page, 101).locator(".assignee")).toHaveText("Assigned to Ada");
  await expect(issue(page, 101).getByRole("button", { name: "Unassign Login page flickers" })).toBeVisible();

  await issue(page, 101).getByRole("button", { name: "Unassign Login page flickers" }).click();

  await expect(issue(page, 101).locator(".assignee")).toHaveText("Unassigned");
  await expect(issue(page, 101).getByRole("button", { name: "Assign to me: Login page flickers" })).toBeVisible();
});

test("changing priority updates the badge, ordering, and persisted state", async ({ page }) => {
  await page.goto("/");

  await expect(titles(page)).resolves.toEqual([
    "#103 Crash on empty cart",
    "#101 Login page flickers",
    "#105 Slow search results",
    "#102 Add CSV export",
    "#104 Update onboarding copy",
  ]);

  await page.getByLabel("Priority for Update onboarding copy").selectOption("high");

  await expect(issue(page, 104).locator(".priority")).toHaveText("Priority: high");
  await expect(titles(page)).resolves.toEqual([
    "#103 Crash on empty cart",
    "#104 Update onboarding copy",
    "#101 Login page flickers",
    "#105 Slow search results",
    "#102 Add CSV export",
  ]);

  await page.getByLabel("Priority for Crash on empty cart").selectOption("low");

  await expect(issue(page, 103).locator(".priority")).toHaveText("Priority: low");
  await expect(titles(page)).resolves.toEqual([
    "#104 Update onboarding copy",
    "#101 Login page flickers",
    "#105 Slow search results",
    "#102 Add CSV export",
    "#103 Crash on empty cart",
  ]);

  await page.reload();

  await expect(issue(page, 104).locator(".priority")).toHaveText("Priority: high");
  await expect(issue(page, 103).locator(".priority")).toHaveText("Priority: low");
  await expect(titles(page)).resolves.toEqual([
    "#104 Update onboarding copy",
    "#101 Login page flickers",
    "#105 Slow search results",
    "#102 Add CSV export",
    "#103 Crash on empty cart",
  ]);
});
