import { expect, test } from "@playwright/test";

const names = (page) => page.locator("tbody tr td:first-child");
const header = (page, name) => page.getByRole("columnheader", { name });
const sortBy = (page, name) => page.getByRole("button", { name }).click();

test.beforeEach(async ({ page }) => {
  await page.goto("/");
});

test("sorts by name ascending then descending with aria-sort", async ({ page }) => {
  await expect(header(page, "Name")).toHaveAttribute("aria-sort", "none");
  await sortBy(page, "Name");
  await expect(names(page)).toHaveText([/^Anvil/, /^Bellows/, /^Chisel set/, /^Drawknife/, /^Emery cloth/, /^Froe/]);
  await expect(header(page, "Name")).toHaveAttribute("aria-sort", "ascending");
  await sortBy(page, "Name");
  await expect(names(page)).toHaveText([/^Froe/, /^Emery cloth/, /^Drawknife/, /^Chisel set/, /^Bellows/, /^Anvil/]);
  await expect(header(page, "Name")).toHaveAttribute("aria-sort", "descending");
  await expect(header(page, "Price")).toHaveAttribute("aria-sort", "none");
});

test("price and stock sort numerically", async ({ page }) => {
  await sortBy(page, "Price");
  await expect(names(page)).toHaveText([/^Emery cloth/, /^Froe/, /^Chisel set/, /^Bellows/, /^Drawknife/, /^Anvil/]);
  await sortBy(page, "Stock");
  await expect(names(page)).toHaveText([/^Bellows/, /^Emery cloth/, /^Drawknife/, /^Anvil/, /^Froe/, /^Chisel set/]);
  await sortBy(page, "Stock");
  await expect(names(page).first()).toHaveText(/^Chisel set/);
});

test("the sort is mirrored in the URL and restored from it", async ({ page }) => {
  await sortBy(page, "Price");
  await sortBy(page, "Price");
  await expect(page).toHaveURL(/\?sort=price&dir=desc$/);
  await page.reload();
  await expect(names(page)).toHaveText([/^Anvil/, /^Drawknife/, /^Bellows/, /^Chisel set/, /^Froe/, /^Emery cloth/]);
  await expect(header(page, "Price")).toHaveAttribute("aria-sort", "descending");
  await page.goto("/?sort=stock&dir=asc");
  await expect(names(page).first()).toHaveText(/^Bellows/);
  await expect(header(page, "Stock")).toHaveAttribute("aria-sort", "ascending");
});

test("zero-stock rows carry the badge", async ({ page }) => {
  await expect(page.getByText("Out of stock")).toHaveCount(2);
  await expect(page.getByRole("row", { name: /Bellows/ })).toContainText("Out of stock");
  await expect(page.getByRole("row", { name: /Anvil/ })).not.toContainText("Out of stock");
});
