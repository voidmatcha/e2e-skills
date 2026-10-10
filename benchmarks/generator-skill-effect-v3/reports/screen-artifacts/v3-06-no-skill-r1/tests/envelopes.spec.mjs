import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page, request }) => {
  const res = await request.post("/api/reset");
  expect(res.ok()).toBeTruthy();
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Groceries" })).toBeVisible();
});

const card = (page, name) =>
  page.locator("article").filter({ has: page.getByRole("heading", { name, exact: true }) });

async function addSpending(page, name, amount) {
  const envelope = card(page, name);
  await envelope.getByRole("textbox").fill(String(amount));
  await envelope.getByRole("button", { name: `Add spending to ${name}` }).click();
}

test("shows the seeded envelopes and total", async ({ page }) => {
  await expect(card(page, "Groceries").locator(".amounts")).toHaveText("$120 of $300");
  await expect(card(page, "Transport").locator(".amounts")).toHaveText("$150 of $150");
  await expect(card(page, "Fun").locator(".amounts")).toHaveText("$0 of $100");
  await expect(card(page, "Groceries").getByRole("progressbar")).toHaveAttribute("aria-valuenow", "40");
  await expect(card(page, "Transport").getByRole("progressbar")).toHaveAttribute("aria-valuenow", "100");
  await expect(card(page, "Fun").getByRole("progressbar")).toHaveAttribute("aria-valuenow", "0");
  await expect(page.getByText("Total $270 of $550")).toBeVisible();
  await expect(page.getByText("Over budget").filter({ visible: true })).toHaveCount(0);
});

test("adding spending updates the amount, progress bar and total", async ({ page }) => {
  await addSpending(page, "Groceries", 90);
  const groceries = card(page, "Groceries");
  await expect(groceries.locator(".amounts")).toHaveText("$210 of $300");
  await expect(groceries.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "70");
  await expect(page.getByText("Total $360 of $550")).toBeVisible();
  await expect(groceries.getByText("Over budget")).toBeHidden();
});

test("spending exactly the limit does not show the badge", async ({ page }) => {
  await addSpending(page, "Fun", 100);
  const fun = card(page, "Fun");
  await expect(fun.locator(".amounts")).toHaveText("$100 of $100");
  await expect(fun.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "100");
  await expect(fun.getByText("Over budget")).toBeHidden();
});

test("exceeding the limit shows the badge and caps the bar at 100", async ({ page }) => {
  await addSpending(page, "Transport", 50);
  const transport = card(page, "Transport");
  await expect(transport.locator(".amounts")).toHaveText("$200 of $150");
  await expect(transport.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "100");
  await expect(transport.getByText("Over budget")).toBeVisible();
  await expect(page.getByText("Total $320 of $550")).toBeVisible();
  await expect(card(page, "Groceries").getByText("Over budget")).toBeHidden();
});

test("reset envelope clears spending and the badge", async ({ page }) => {
  await addSpending(page, "Transport", 10);
  const transport = card(page, "Transport");
  await expect(transport.getByText("Over budget")).toBeVisible();
  await transport.getByRole("button", { name: "Reset Transport" }).click();
  await expect(transport.locator(".amounts")).toHaveText("$0 of $150");
  await expect(transport.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "0");
  await expect(transport.getByText("Over budget")).toBeHidden();
  await expect(page.getByText("Total $120 of $550")).toBeVisible();
});

test("spending survives a reload", async ({ page }) => {
  await addSpending(page, "Fun", 40);
  await expect(card(page, "Fun").locator(".amounts")).toHaveText("$40 of $100");
  await page.reload();
  await expect(card(page, "Fun").locator(".amounts")).toHaveText("$40 of $100");
  await expect(card(page, "Fun").getByRole("progressbar")).toHaveAttribute("aria-valuenow", "40");
  await expect(page.getByText("Total $310 of $550")).toBeVisible();
});
