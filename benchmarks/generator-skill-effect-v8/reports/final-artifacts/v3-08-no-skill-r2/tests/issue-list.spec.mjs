import { expect, test } from "@playwright/test";

const issue = (page, id, title) =>
  page.locator("article").filter({
    has: page.getByRole("heading", { name: `#${id} ${title}` }),
  });

const issueHeadings = (page) => page.locator("article h2");

test.beforeEach(async ({ request }) => {
  await request.post("/api/reset");
});

test("assigns and unassigns an issue for Ada and updates filter counts", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByRole("button", { name: "All (5)" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Mine (1)" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Unassigned (3)" })).toBeVisible();

  const loginIssue = issue(page, 101, "Login page flickers");
  await loginIssue.getByRole("button", { name: "Assign to me: Login page flickers" }).click();

  await expect(loginIssue.getByText("Assigned to Ada")).toBeVisible();
  await expect(loginIssue.getByRole("button", { name: "Unassign Login page flickers" })).toBeVisible();
  await expect(page.getByRole("button", { name: "All (5)" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Mine (2)" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Unassigned (2)" })).toBeVisible();

  await page.getByRole("button", { name: "Mine (2)" }).click();
  await expect(issueHeadings(page)).toHaveText([
    "#101 Login page flickers",
    "#105 Slow search results",
  ]);

  await loginIssue.getByRole("button", { name: "Unassign Login page flickers" }).click();
  await expect(page.getByRole("button", { name: "Mine (1)" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Unassigned (3)" })).toBeVisible();
  await expect(issueHeadings(page)).toHaveText(["#105 Slow search results"]);
});

test("persists assignments and priorities across reloads", async ({ page }) => {
  await page.goto("/");

  const csvIssue = issue(page, 102, "Add CSV export");
  await csvIssue.getByLabel("Priority for Add CSV export").selectOption("high");
  await expect(csvIssue.getByText("Priority: high")).toBeVisible();

  await issue(page, 104, "Update onboarding copy")
    .getByRole("button", { name: "Assign to me: Update onboarding copy" })
    .click();
  await expect(issue(page, 104, "Update onboarding copy").getByText("Assigned to Ada")).toBeVisible();

  await expect(issueHeadings(page)).toHaveText([
    "#102 Add CSV export",
    "#103 Crash on empty cart",
    "#101 Login page flickers",
    "#105 Slow search results",
    "#104 Update onboarding copy",
  ]);

  await page.reload();

  await expect(issue(page, 102, "Add CSV export").getByText("Priority: high")).toBeVisible();
  await expect(issue(page, 104, "Update onboarding copy").getByText("Assigned to Ada")).toBeVisible();
  await expect(issue(page, 104, "Update onboarding copy").getByRole("button", { name: "Unassign Update onboarding copy" })).toBeVisible();
  await expect(issueHeadings(page)).toHaveText([
    "#102 Add CSV export",
    "#103 Crash on empty cart",
    "#101 Login page flickers",
    "#105 Slow search results",
    "#104 Update onboarding copy",
  ]);
});
