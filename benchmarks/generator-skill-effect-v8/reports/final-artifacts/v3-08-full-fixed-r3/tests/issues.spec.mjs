import { expect, test } from "@playwright/test";

const escapeRegExp = (value) => value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

const issueCard = (page, title) =>
  page.locator("article").filter({
    has: page.getByRole("heading", { name: new RegExp(`^#\\d+ ${escapeRegExp(title)}$`) }),
  });

const issueHeadings = (page) => page.getByRole("heading", { level: 2 });

test.beforeEach(async ({ page }) => {
  await page.request.post("/api/reset");
  await page.goto("/");
  await expect(page.getByRole("button", { name: /^All \(5\)$/ })).toHaveAttribute("aria-pressed", "true");
});

test("filters Mine to Ada's issues with live assignment counts", async ({ page }) => {
  const crashIssue = issueCard(page, "Crash on empty cart");
  const assignRequest = page.waitForRequest(
    (request) =>
      request.method() === "PATCH" &&
      new URL(request.url()).pathname === "/api/issues/103",
  );

  await crashIssue.getByRole("button", { name: "Assign to me: Crash on empty cart" }).click();

  const request = await assignRequest;
  expect(request.postDataJSON()).toEqual({ assignee: "Ada" });
  await expect(crashIssue.getByText("Assigned to Ada")).toBeVisible();
  await expect(crashIssue.getByRole("button", { name: "Unassign Crash on empty cart" })).toBeVisible();
  await expect(page.getByRole("button", { name: /^All \(5\)$/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /^Mine \(2\)$/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /^Unassigned \(2\)$/ })).toBeVisible();

  await page.reload();
  await expect(issueCard(page, "Crash on empty cart").getByText("Assigned to Ada")).toBeVisible();
  await page.getByRole("button", { name: /^Mine \(2\)$/ }).click();

  await expect(issueHeadings(page)).toHaveText([
    "#103 Crash on empty cart",
    "#105 Slow search results",
  ]);

  const unassignRequest = page.waitForRequest(
    (request) =>
      request.method() === "PATCH" &&
      new URL(request.url()).pathname === "/api/issues/103",
  );
  await issueCard(page, "Crash on empty cart")
    .getByRole("button", { name: "Unassign Crash on empty cart" })
    .click();

  const unassign = await unassignRequest;
  expect(unassign.postDataJSON()).toEqual({ assignee: null });
  await expect(page.getByRole("button", { name: /^Mine \(1\)$/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /^Unassigned \(3\)$/ })).toBeVisible();

  await page.reload();
  await expect(issueCard(page, "Crash on empty cart").getByText("Unassigned")).toBeVisible();
});

test("updates priority badges, ordering, and stored priority", async ({ page }) => {
  const onboardingIssue = issueCard(page, "Update onboarding copy");
  const priorityRequest = page.waitForRequest(
    (request) =>
      request.method() === "PATCH" &&
      new URL(request.url()).pathname === "/api/issues/104",
  );

  await onboardingIssue.getByLabel("Priority for Update onboarding copy").selectOption("high");

  const request = await priorityRequest;
  expect(request.postDataJSON()).toEqual({ priority: "high" });
  await expect(onboardingIssue.getByText("Priority: high")).toBeVisible();
  await expect(issueHeadings(page)).toHaveText([
    "#103 Crash on empty cart",
    "#104 Update onboarding copy",
    "#101 Login page flickers",
    "#105 Slow search results",
    "#102 Add CSV export",
  ]);

  await page.reload();
  await expect(issueCard(page, "Update onboarding copy").getByText("Priority: high")).toBeVisible();
  await expect(issueHeadings(page)).toHaveText([
    "#103 Crash on empty cart",
    "#104 Update onboarding copy",
    "#101 Login page flickers",
    "#105 Slow search results",
    "#102 Add CSV export",
  ]);
});
