import { expect, test } from "@playwright/test";

const issueCard = (page, id) =>
  page.getByRole("article").filter({
    has: page.getByRole("heading", { name: new RegExp(`^#${id}\\b`) }),
  });

const issueHeadings = (page) => page.getByRole("article").getByRole("heading");

test.beforeEach(async ({ page }) => {
  await page.request.post("/api/reset");
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Issues", exact: true })).toBeVisible();
});

test("shows seeded issues and filters Ada's assigned issues", async ({ page }) => {
  await expect(issueHeadings(page)).toHaveText([
    "#103 Crash on empty cart",
    "#101 Login page flickers",
    "#105 Slow search results",
    "#102 Add CSV export",
    "#104 Update onboarding copy",
  ]);
  await expect(page.getByRole("button", { name: "All (5)", exact: true })).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByRole("button", { name: "Mine (1)", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Unassigned (3)", exact: true })).toBeVisible();
  await expect(issueCard(page, 105)).toContainText("Assigned to Ada");
  await expect(issueCard(page, 102)).toContainText("Assigned to Grace");

  await page.getByRole("button", { name: "Mine (1)", exact: true }).click();

  await expect(issueHeadings(page)).toHaveText(["#105 Slow search results"]);
});

test("assigns and unassigns an issue for Ada with persisted counts", async ({ page }) => {
  const assignRequest = page.waitForRequest((request) => {
    if (request.method() !== "PATCH" || !request.url().endsWith("/api/issues/101")) return false;
    return request.postDataJSON().assignee === "Ada";
  });

  await issueCard(page, 101)
    .getByRole("button", { name: "Assign to me: Login page flickers", exact: true })
    .click();
  await assignRequest;

  await expect(issueCard(page, 101)).toContainText("Assigned to Ada");
  await expect(
    issueCard(page, 101).getByRole("button", { name: "Unassign Login page flickers", exact: true }),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "Mine (2)", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Unassigned (2)", exact: true })).toBeVisible();

  await page.reload();
  await expect(issueCard(page, 101)).toContainText("Assigned to Ada");

  const unassignRequest = page.waitForRequest((request) => {
    if (request.method() !== "PATCH" || !request.url().endsWith("/api/issues/101")) return false;
    return request.postDataJSON().assignee === null;
  });

  await issueCard(page, 101).getByRole("button", { name: "Unassign Login page flickers", exact: true }).click();
  await unassignRequest;

  await expect(issueCard(page, 101)).toContainText("Unassigned");
  await expect(
    issueCard(page, 101).getByRole("button", { name: "Assign to me: Login page flickers", exact: true }),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "Mine (1)", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Unassigned (3)", exact: true })).toBeVisible();

  await page.reload();
  await expect(issueCard(page, 101)).toContainText("Unassigned");
});

test("updates priority badges, ordering, and persisted priority", async ({ page }) => {
  const priorityRequest = page.waitForRequest((request) => {
    if (request.method() !== "PATCH" || !request.url().endsWith("/api/issues/102")) return false;
    return request.postDataJSON().priority === "high";
  });

  await issueCard(page, 102).getByLabel("Priority for Add CSV export", { exact: true }).selectOption("high");
  await priorityRequest;

  await expect(issueCard(page, 102).getByText("Priority: high", { exact: true })).toBeVisible();
  await expect(issueHeadings(page)).toHaveText([
    "#102 Add CSV export",
    "#103 Crash on empty cart",
    "#101 Login page flickers",
    "#105 Slow search results",
    "#104 Update onboarding copy",
  ]);

  await page.reload();
  await expect(issueCard(page, 102).getByText("Priority: high", { exact: true })).toBeVisible();
  await expect(issueHeadings(page)).toHaveText([
    "#102 Add CSV export",
    "#103 Crash on empty cart",
    "#101 Login page flickers",
    "#105 Slow search results",
    "#104 Update onboarding copy",
  ]);
});
