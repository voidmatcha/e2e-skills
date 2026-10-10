import { expect, test } from "@playwright/test";

function envelopeCard(page, name) {
  return page.locator("article").filter({
    has: page.getByRole("heading", { name, exact: true }),
  });
}

async function expectOverBudgetBadgeHidden(card) {
  const badge = card.getByText("Over budget", { exact: true });
  await expect(badge).toHaveCount(1);
  await expect(badge).toBeHidden();
}

test.beforeEach(async ({ page, request }) => {
  await request.post("/api/reset");
  await page.goto("/");
});

test("shows seeded envelope totals and progress", async ({ page }) => {
  const groceries = envelopeCard(page, "Groceries");
  const transport = envelopeCard(page, "Transport");
  const fun = envelopeCard(page, "Fun");

  await expect(page.getByText("Total $270 of $550")).toBeVisible();
  await expect(groceries.getByRole("heading", { name: "Groceries", exact: true })).toBeVisible();
  await expect(groceries.getByText("$120 of $300")).toBeVisible();
  await expect(page.getByRole("progressbar", { name: "Groceries spending", exact: true })).toHaveAttribute("aria-valuenow", "40");
  await expect(transport.getByRole("heading", { name: "Transport", exact: true })).toBeVisible();
  await expect(transport.getByText("$150 of $150")).toBeVisible();
  await expect(page.getByRole("progressbar", { name: "Transport spending", exact: true })).toHaveAttribute("aria-valuenow", "100");
  await expect(fun.getByRole("heading", { name: "Fun", exact: true })).toBeVisible();
  await expect(fun.getByText("$0 of $100")).toBeVisible();
  await expect(page.getByRole("progressbar", { name: "Fun spending", exact: true })).toHaveAttribute("aria-valuenow", "0");
  await expectOverBudgetBadgeHidden(groceries);
  await expectOverBudgetBadgeHidden(transport);
  await expectOverBudgetBadgeHidden(fun);
});

test("adds spending to an envelope and keeps it after reload", async ({ page }) => {
  const spendRequest = page.waitForRequest((request) => {
    return request.method() === "POST" && request.url().endsWith("/api/envelopes/groceries/spend");
  });

  await page.getByRole("textbox", { name: "Add spending Groceries", exact: true }).fill("30");
  await page.getByRole("button", { name: "Add spending to Groceries", exact: true }).click();

  const request = await spendRequest;
  expect(request.postDataJSON()).toEqual({ amount: 30 });
  await expect(page.getByText("Total $300 of $550")).toBeVisible();
  await expect(page.getByText("$150 of $300")).toBeVisible();
  await expect(page.getByRole("progressbar", { name: "Groceries spending", exact: true })).toHaveAttribute("aria-valuenow", "50");

  await page.reload();

  await expect(page.getByText("Total $300 of $550")).toBeVisible();
  await expect(page.getByText("$150 of $300")).toBeVisible();
  await expect(page.getByRole("progressbar", { name: "Groceries spending", exact: true })).toHaveAttribute("aria-valuenow", "50");
});

test("shows the over budget badge only after the limit is exceeded and removes it on reset", async ({ page }) => {
  const fun = envelopeCard(page, "Fun");

  await page.getByRole("textbox", { name: "Add spending Fun", exact: true }).fill("100");
  await page.getByRole("button", { name: "Add spending to Fun", exact: true }).click();

  await expect(page.getByText("Total $370 of $550")).toBeVisible();
  await expect(fun.getByText("$100 of $100")).toBeVisible();
  await expect(page.getByRole("progressbar", { name: "Fun spending", exact: true })).toHaveAttribute("aria-valuenow", "100");
  await expectOverBudgetBadgeHidden(fun);

  await page.getByRole("textbox", { name: "Add spending Fun", exact: true }).fill("1");
  await page.getByRole("button", { name: "Add spending to Fun", exact: true }).click();

  await expect(page.getByText("Total $371 of $550")).toBeVisible();
  await expect(fun.getByText("$101 of $100")).toBeVisible();
  await expect(page.getByRole("progressbar", { name: "Fun spending", exact: true })).toHaveAttribute("aria-valuenow", "100");
  await expect(fun.getByText("Over budget", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: "Reset Fun", exact: true }).click();

  await expect(page.getByText("Total $270 of $550")).toBeVisible();
  await expect(fun.getByText("$0 of $100")).toBeVisible();
  await expect(page.getByRole("progressbar", { name: "Fun spending", exact: true })).toHaveAttribute("aria-valuenow", "0");
  await expectOverBudgetBadgeHidden(fun);
});
