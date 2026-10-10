import { expect, test } from "@playwright/test";

const envelope = (page, name) =>
  page.locator("article").filter({ has: page.getByRole("heading", { name }) });

const spendingInput = (card) => card.locator("input");

test.beforeEach(async ({ request }) => {
  await request.post("/api/reset");
});

test("shows the starting budget envelopes and total", async ({ page }) => {
  await page.goto("/");

  await expect(page.locator("article")).toHaveCount(3);
  await expect(page.getByText("Total $270 of $550")).toBeVisible();

  await expect(envelope(page, "Groceries").getByText("$120 of $300")).toBeVisible();
  await expect(envelope(page, "Groceries").getByRole("progressbar")).toHaveAttribute("aria-valuenow", "40");

  await expect(envelope(page, "Transport").getByText("$150 of $150")).toBeVisible();
  await expect(envelope(page, "Transport").getByRole("progressbar")).toHaveAttribute("aria-valuenow", "100");
  await expect(envelope(page, "Transport").getByText("Over budget")).toBeHidden();

  await expect(envelope(page, "Fun").getByText("$0 of $100")).toBeVisible();
  await expect(envelope(page, "Fun").getByRole("progressbar")).toHaveAttribute("aria-valuenow", "0");
});

test("adds spending, updates totals and keeps the spending after reload", async ({ page }) => {
  await page.goto("/");

  const groceries = envelope(page, "Groceries");
  await spendingInput(groceries).fill("60");
  await groceries.getByRole("button", { name: "Add spending to Groceries" }).click();

  await expect(groceries.getByText("$180 of $300")).toBeVisible();
  await expect(groceries.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "60");
  await expect(page.getByText("Total $330 of $550")).toBeVisible();

  await page.reload();

  await expect(envelope(page, "Groceries").getByText("$180 of $300")).toBeVisible();
  await expect(page.getByText("Total $330 of $550")).toBeVisible();
});

test("only shows the over budget badge above the limit and reset clears it", async ({ page }) => {
  await page.goto("/");

  const fun = envelope(page, "Fun");
  await spendingInput(fun).fill("100");
  await fun.getByRole("button", { name: "Add spending to Fun" }).click();

  await expect(fun.getByText("$100 of $100")).toBeVisible();
  await expect(fun.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "100");
  await expect(fun.getByText("Over budget")).toBeHidden();

  await spendingInput(fun).fill("25");
  await fun.getByRole("button", { name: "Add spending to Fun" }).click();

  await expect(fun.getByText("$125 of $100")).toBeVisible();
  await expect(fun.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "100");
  await expect(fun.getByText("Over budget")).toBeVisible();
  await expect(page.getByText("Total $395 of $550")).toBeVisible();

  await fun.getByRole("button", { name: "Reset Fun" }).click();

  await expect(fun.getByText("$0 of $100")).toBeVisible();
  await expect(fun.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "0");
  await expect(fun.getByText("Over budget")).toBeHidden();
  await expect(page.getByText("Total $270 of $550")).toBeVisible();
});
