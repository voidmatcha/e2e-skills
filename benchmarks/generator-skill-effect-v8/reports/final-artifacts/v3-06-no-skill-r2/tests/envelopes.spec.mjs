import { expect, test } from "@playwright/test";

const card = (page, name) =>
  page.locator(".envelope").filter({ has: page.getByRole("heading", { name }) });

const addSpending = async (page, name, amount) => {
  const envelope = card(page, name);
  await envelope.locator("input").fill(String(amount));
  await envelope.getByRole("button", { name: `Add spending to ${name}` }).click();
};

test.beforeEach(async ({ page }) => {
  await page.request.post("/api/reset");
});

test("shows the starting budget envelopes", async ({ page }) => {
  await page.goto("/");

  await expect(page.locator(".envelope")).toHaveCount(3);
  await expect(page.getByText("Total $270 of $550")).toBeVisible();

  await expect(card(page, "Groceries").getByText("$120 of $300")).toBeVisible();
  await expect(card(page, "Groceries").getByRole("progressbar", { name: "Groceries spending" })).toHaveAttribute(
    "aria-valuenow",
    "40",
  );
  await expect(card(page, "Groceries").getByText("Over budget")).toBeHidden();

  await expect(card(page, "Transport").getByText("$150 of $150")).toBeVisible();
  await expect(card(page, "Transport").getByRole("progressbar", { name: "Transport spending" })).toHaveAttribute(
    "aria-valuenow",
    "100",
  );
  await expect(card(page, "Transport").getByText("Over budget")).toBeHidden();

  await expect(card(page, "Fun").getByText("$0 of $100")).toBeVisible();
  await expect(card(page, "Fun").getByRole("progressbar", { name: "Fun spending" })).toHaveAttribute(
    "aria-valuenow",
    "0",
  );
  await expect(card(page, "Fun").getByText("Over budget")).toBeHidden();
});

test("adds spending, caps progress, totals every envelope, and survives reload", async ({ page }) => {
  await page.goto("/");

  await addSpending(page, "Groceries", 30);
  await expect(card(page, "Groceries").getByText("$150 of $300")).toBeVisible();
  await expect(card(page, "Groceries").getByRole("progressbar", { name: "Groceries spending" })).toHaveAttribute(
    "aria-valuenow",
    "50",
  );
  await expect(card(page, "Groceries").getByText("Over budget")).toBeHidden();
  await expect(page.getByText("Total $300 of $550")).toBeVisible();

  await addSpending(page, "Transport", 1);
  await expect(card(page, "Transport").getByText("$151 of $150")).toBeVisible();
  await expect(card(page, "Transport").getByRole("progressbar", { name: "Transport spending" })).toHaveAttribute(
    "aria-valuenow",
    "100",
  );
  await expect(card(page, "Transport").getByText("Over budget")).toBeVisible();
  await expect(page.getByText("Total $301 of $550")).toBeVisible();

  await page.reload();
  await expect(card(page, "Groceries").getByText("$150 of $300")).toBeVisible();
  await expect(card(page, "Transport").getByText("$151 of $150")).toBeVisible();
  await expect(card(page, "Transport").getByText("Over budget")).toBeVisible();
  await expect(page.getByText("Total $301 of $550")).toBeVisible();
});

test("resets an envelope to zero and clears its over-budget badge", async ({ page }) => {
  await page.goto("/");

  await addSpending(page, "Fun", 160);
  await expect(card(page, "Fun").getByText("$160 of $100")).toBeVisible();
  await expect(card(page, "Fun").getByRole("progressbar", { name: "Fun spending" })).toHaveAttribute(
    "aria-valuenow",
    "100",
  );
  await expect(card(page, "Fun").getByText("Over budget")).toBeVisible();
  await expect(page.getByText("Total $430 of $550")).toBeVisible();

  await card(page, "Fun").getByRole("button", { name: "Reset Fun" }).click();
  await expect(card(page, "Fun").getByText("$0 of $100")).toBeVisible();
  await expect(card(page, "Fun").getByRole("progressbar", { name: "Fun spending" })).toHaveAttribute(
    "aria-valuenow",
    "0",
  );
  await expect(card(page, "Fun").getByText("Over budget")).toBeHidden();
  await expect(page.getByText("Total $270 of $550")).toBeVisible();
});
