import { expect, test } from "@playwright/test";

test.beforeEach(async ({ request }) => {
  await request.post("/api/reset");
});

const issue = (page, id) =>
  page.locator("article").filter({
    has: page.getByRole("heading", { name: new RegExp(`^#${id} `) }),
  });

const issueIds = async (page) =>
  (await page.locator("article h2").allTextContents()).map((text) => Number(text.match(/^#(\d+)/)[1]));

test("assigns and unassigns issues for Ada and updates filter counts", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByRole("button", { name: "All (5)" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Mine (1)" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Unassigned (3)" })).toBeVisible();
  await expect(issue(page, 101)).toContainText("Unassigned");

  await issue(page, 101).getByRole("button", { name: "Assign to me: Login page flickers" }).click();

  await expect(issue(page, 101)).toContainText("Assigned to Ada");
  await expect(issue(page, 101).getByRole("button", { name: "Unassign Login page flickers" })).toBeVisible();
  await expect(page.getByRole("button", { name: "All (5)" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Mine (2)" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Unassigned (2)" })).toBeVisible();

  await page.getByRole("button", { name: "Mine (2)" }).click();
  await expect(page.locator("article")).toHaveCount(2);
  await expect(issueIds(page)).resolves.toEqual([101, 105]);
  await expect(issue(page, 102)).toHaveCount(0);

  await issue(page, 101).getByRole("button", { name: "Unassign Login page flickers" }).click();

  await expect(issue(page, 101)).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Mine (1)" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Unassigned (3)" })).toBeVisible();

  await page.getByRole("button", { name: "Unassigned (3)" }).click();
  await expect(issue(page, 101)).toContainText("Unassigned");
});

test("updates priority badges, ordering, and persists changes across reload", async ({ page }) => {
  await page.goto("/");

  await expect(issueIds(page)).resolves.toEqual([103, 101, 105, 102, 104]);

  await issue(page, 104).getByLabel("Priority for Update onboarding copy").selectOption("high");
  await expect(issue(page, 104).locator(".priority")).toHaveText("Priority: high");
  await expect(issueIds(page)).resolves.toEqual([103, 104, 101, 105, 102]);

  await issue(page, 101).getByRole("button", { name: "Assign to me: Login page flickers" }).click();
  await issue(page, 101).getByLabel("Priority for Login page flickers").selectOption("low");
  await expect(issue(page, 101).locator(".priority")).toHaveText("Priority: low");
  await expect(issueIds(page)).resolves.toEqual([103, 104, 105, 101, 102]);

  await page.reload();

  await expect(issue(page, 101)).toContainText("Assigned to Ada");
  await expect(issue(page, 101).locator(".priority")).toHaveText("Priority: low");
  await expect(issue(page, 104).locator(".priority")).toHaveText("Priority: high");
  await expect(issueIds(page)).resolves.toEqual([103, 104, 105, 101, 102]);
  await expect(page.getByRole("button", { name: "Mine (2)" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Unassigned (2)" })).toBeVisible();
});
