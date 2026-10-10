import { expect, test } from "@playwright/test";

const card = (page, name) => page.getByRole("article").filter({ has: page.getByRole("heading", { name }) });
const bar = (page, name) => page.getByRole("progressbar", { name: `${name} spending` });
const total = (page) => page.getByText(/^Total \$\d+ of \$\d+$/);

async function spend(page, name, amount) {
  await page.getByRole("textbox", { name: `Add spending ${name}` }).fill(String(amount));
  await page.getByRole("button", { name: `Add spending to ${name}` }).click();
}

test.beforeEach(async ({ page }) => {
  await page.request.post("/api/reset");
  await page.goto("/");
  await expect(total(page)).toHaveText("Total $270 of $550");
});

test("adding spending updates the card, the bar and the total, and persists", async ({ page }) => {
  await expect(bar(page, "Groceries")).toHaveAttribute("aria-valuenow", "40");
  await spend(page, "Groceries", 60);
  await expect(card(page, "Groceries")).toContainText("$180 of $300");
  await expect(bar(page, "Groceries")).toHaveAttribute("aria-valuenow", "60");
  await expect(total(page)).toHaveText("Total $330 of $550");
  await page.reload();
  await expect(card(page, "Groceries")).toContainText("$180 of $300");
  await expect(bar(page, "Groceries")).toHaveAttribute("aria-valuenow", "60");
  await expect(total(page)).toHaveText("Total $330 of $550");
});

test("the badge appears only above the limit and reset clears it", async ({ page }) => {
  await expect(card(page, "Transport").getByText("Over budget")).toBeHidden();
  await expect(bar(page, "Transport")).toHaveAttribute("aria-valuenow", "100");
  await spend(page, "Transport", 1);
  await expect(card(page, "Transport")).toContainText("$151 of $150");
  await expect(card(page, "Transport").getByText("Over budget")).toBeVisible();
  await expect(bar(page, "Transport")).toHaveAttribute("aria-valuenow", "100");
  await page.getByRole("button", { name: "Reset Transport" }).click();
  await expect(card(page, "Transport")).toContainText("$0 of $150");
  await expect(card(page, "Transport").getByText("Over budget")).toBeHidden();
  await expect(bar(page, "Transport")).toHaveAttribute("aria-valuenow", "0");
  await expect(total(page)).toHaveText("Total $120 of $550");
});
