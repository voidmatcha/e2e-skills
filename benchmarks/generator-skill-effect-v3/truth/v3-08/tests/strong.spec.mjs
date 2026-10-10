import { expect, test } from "@playwright/test";

const cards = (page) => page.getByRole("article");
const card = (page, title) => cards(page).filter({ has: page.getByRole("heading", { name: title }) });
const chip = (page, label) => page.getByRole("group", { name: "Filters" }).getByRole("button", { name: new RegExp(`^${label} \\(\\d+\\)$`) });

test.beforeEach(async ({ page }) => {
  await page.request.post("/api/reset");
  await page.goto("/");
  await expect(cards(page)).toHaveCount(5);
  await expect(chip(page, "Mine")).toHaveText("Mine (1)");
});

test("assign and unassign update the card, the counts and persist", async ({ page }) => {
  await page.getByRole("button", { name: "Assign to me: Login page flickers" }).click();
  await expect(card(page, "#101 Login page flickers")).toContainText("Assigned to Ada");
  await expect(page.getByRole("button", { name: "Unassign Login page flickers" })).toBeVisible();
  await expect(chip(page, "Mine")).toHaveText("Mine (2)");
  await expect(chip(page, "Unassigned")).toHaveText("Unassigned (2)");
  await page.reload();
  await expect(card(page, "#101 Login page flickers")).toContainText("Assigned to Ada");
  await page.getByRole("button", { name: "Unassign Login page flickers" }).click();
  await expect(card(page, "#101 Login page flickers")).toContainText("Unassigned");
  await expect(chip(page, "Mine")).toHaveText("Mine (1)");
});

test("the Mine chip filters to Ada's issues", async ({ page }) => {
  await chip(page, "Mine").click();
  await expect(cards(page)).toHaveText([/#105 Slow search results/]);
  await expect(chip(page, "Mine")).toHaveAttribute("aria-pressed", "true");
  await chip(page, "Unassigned").click();
  await expect(cards(page)).toHaveCount(3);
  await chip(page, "All").click();
  await expect(cards(page)).toHaveCount(5);
});

test("priority changes the badge, the order, and persists", async ({ page }) => {
  await expect(cards(page).first()).toContainText("#103 Crash on empty cart");
  await page.getByRole("combobox", { name: "Priority for Update onboarding copy" }).selectOption("high");
  await expect(card(page, "#104 Update onboarding copy")).toContainText("Priority: high");
  await expect(cards(page).nth(0)).toContainText("#103");
  await expect(cards(page).nth(1)).toContainText("#104");
  await expect(cards(page).last()).toContainText("#102 Add CSV export");
  await page.reload();
  await expect(card(page, "#104 Update onboarding copy")).toContainText("Priority: high");
  await expect(cards(page).nth(1)).toContainText("#104");
});
