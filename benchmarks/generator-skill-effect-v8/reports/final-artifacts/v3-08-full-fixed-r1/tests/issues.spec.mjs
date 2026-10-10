import { expect, test } from "@playwright/test";

const issueCard = (page, title) =>
  page.getByRole("article").filter({ has: page.getByRole("heading", { name: new RegExp(`^#\\d+ ${title}$`) }) });

const issueHeadings = (page) => page.getByRole("article").getByRole("heading");

const waitForIssuePatch = (page, id, expectedBody) =>
  page.waitForRequest((request) => {
    if (request.method() !== "PATCH" || !request.url().endsWith(`/api/issues/${id}`)) return false;

    const body = JSON.parse(request.postData() ?? "{}");
    return Object.entries(expectedBody).every(([key, value]) => body[key] === value);
  });

test.beforeEach(async ({ page }) => {
  const reset = await page.request.post("/api/reset");
  expect(reset.status()).toBe(200);

  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Issues", exact: true })).toBeVisible();
});

test("assigns and unassigns Ada's issues with live filter counts", async ({ page }) => {
  await expect(page.getByRole("button", { name: "All (5)", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Mine (1)", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Unassigned (3)", exact: true })).toBeVisible();
  await expect(issueHeadings(page)).toHaveText([
    "#103 Crash on empty cart",
    "#101 Login page flickers",
    "#105 Slow search results",
    "#102 Add CSV export",
    "#104 Update onboarding copy",
  ]);

  const loginIssue = issueCard(page, "Login page flickers");
  const assignRequest = waitForIssuePatch(page, 101, { assignee: "Ada" });
  await loginIssue.getByRole("button", { name: "Assign to me: Login page flickers" }).click();
  await assignRequest;

  await expect(loginIssue).toContainText("Assigned to Ada");
  await expect(loginIssue.getByRole("button", { name: "Unassign Login page flickers" })).toBeVisible();
  await expect(page.getByRole("button", { name: "All (5)", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Mine (2)", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Unassigned (2)", exact: true })).toBeVisible();

  await page.getByRole("button", { name: "Mine (2)", exact: true }).click();
  await expect(issueHeadings(page)).toHaveText([
    "#101 Login page flickers",
    "#105 Slow search results",
  ]);

  await page.reload();
  await expect(page.getByRole("button", { name: "Mine (2)", exact: true })).toBeVisible();
  await expect(issueCard(page, "Login page flickers")).toContainText("Assigned to Ada");

  const unassignRequest = waitForIssuePatch(page, 101, { assignee: null });
  await loginIssue.getByRole("button", { name: "Unassign Login page flickers" }).click();
  await unassignRequest;
  await expect(page.getByRole("button", { name: "Mine (1)", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Unassigned (3)", exact: true })).toBeVisible();

  await page.getByRole("button", { name: "All (5)", exact: true }).click();
  await expect(loginIssue).toContainText("Unassigned");
  await expect(loginIssue.getByRole("button", { name: "Assign to me: Login page flickers" })).toBeVisible();
});

test("updates priority badges, ordering, and persists priority changes", async ({ page }) => {
  const csvIssue = issueCard(page, "Add CSV export");

  const csvPriorityRequest = waitForIssuePatch(page, 102, { priority: "high" });
  await csvIssue.getByLabel("Priority for Add CSV export").selectOption("high");
  await csvPriorityRequest;
  await expect(csvIssue.getByText("Priority: high")).toBeVisible();
  await expect(issueHeadings(page)).toHaveText([
    "#102 Add CSV export",
    "#103 Crash on empty cart",
    "#101 Login page flickers",
    "#105 Slow search results",
    "#104 Update onboarding copy",
  ]);

  await page.reload();
  await expect(issueCard(page, "Add CSV export").getByText("Priority: high")).toBeVisible();
  await expect(issueHeadings(page)).toHaveText([
    "#102 Add CSV export",
    "#103 Crash on empty cart",
    "#101 Login page flickers",
    "#105 Slow search results",
    "#104 Update onboarding copy",
  ]);

  const loginPriorityRequest = waitForIssuePatch(page, 101, { priority: "low" });
  await issueCard(page, "Login page flickers").getByLabel("Priority for Login page flickers").selectOption("low");
  await loginPriorityRequest;
  await expect(issueCard(page, "Login page flickers").getByText("Priority: low")).toBeVisible();
  await expect(issueHeadings(page)).toHaveText([
    "#102 Add CSV export",
    "#103 Crash on empty cart",
    "#105 Slow search results",
    "#101 Login page flickers",
    "#104 Update onboarding copy",
  ]);
});
