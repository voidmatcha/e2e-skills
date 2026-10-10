import { expect, test } from "@playwright/test";

const expectedRows = {
  name: {
    asc: [
      "Anvil$120.002",
      "Bellows Out of stock$42.000",
      "Chisel set$15.0014",
      "Drawknife$68.001",
      "Emery cloth Out of stock$7.000",
      "Froe$9.506",
    ],
    desc: [
      "Froe$9.506",
      "Emery cloth Out of stock$7.000",
      "Drawknife$68.001",
      "Chisel set$15.0014",
      "Bellows Out of stock$42.000",
      "Anvil$120.002",
    ],
  },
  price: {
    asc: [
      "Emery cloth Out of stock$7.000",
      "Froe$9.506",
      "Chisel set$15.0014",
      "Bellows Out of stock$42.000",
      "Drawknife$68.001",
      "Anvil$120.002",
    ],
    desc: [
      "Anvil$120.002",
      "Drawknife$68.001",
      "Bellows Out of stock$42.000",
      "Chisel set$15.0014",
      "Froe$9.506",
      "Emery cloth Out of stock$7.000",
    ],
  },
  stock: {
    asc: [
      "Bellows Out of stock$42.000",
      "Emery cloth Out of stock$7.000",
      "Drawknife$68.001",
      "Anvil$120.002",
      "Froe$9.506",
      "Chisel set$15.0014",
    ],
    desc: [
      "Chisel set$15.0014",
      "Froe$9.506",
      "Anvil$120.002",
      "Drawknife$68.001",
      "Bellows Out of stock$42.000",
      "Emery cloth Out of stock$7.000",
    ],
  },
};

function header(page, name) {
  return page.getByRole("columnheader").filter({
    has: page.getByRole("button", { name, exact: true }),
  });
}

function rows(page) {
  return page.getByRole("table").locator("tbody").getByRole("row");
}

async function expectSortState(page, activeColumn, direction) {
  const states = [
    ["Name", activeColumn === "Name" ? direction : "none"],
    ["Price", activeColumn === "Price" ? direction : "none"],
    ["Stock", activeColumn === "Stock" ? direction : "none"],
  ];

  for (const [name, state] of states) {
    await expect(header(page, name)).toHaveAttribute("aria-sort", state);
  }
}

test.describe("inventory table sorting", () => {
  test("sorts by name and updates header state", async ({ page }) => {
    await page.goto("/");

    await page.getByRole("button", { name: "Name", exact: true }).click();
    await expect(rows(page)).toHaveText(expectedRows.name.asc);
    await expect(page).toHaveURL("/?sort=name&dir=asc");
    await expectSortState(page, "Name", "ascending");

    await page.getByRole("button", { name: "Name", exact: true }).click();
    await expect(rows(page)).toHaveText(expectedRows.name.desc);
    await expect(page).toHaveURL("/?sort=name&dir=desc");
    await expectSortState(page, "Name", "descending");
  });

  test("sorts price numerically and restores it from the URL", async ({ page }) => {
    await page.goto("/");

    await page.getByRole("button", { name: "Price", exact: true }).click();
    await expect(rows(page)).toHaveText(expectedRows.price.asc);
    await expect(page).toHaveURL("/?sort=price&dir=asc");
    await expectSortState(page, "Price", "ascending");

    await page.getByRole("button", { name: "Price", exact: true }).click();
    await expect(rows(page)).toHaveText(expectedRows.price.desc);
    await expect(page).toHaveURL("/?sort=price&dir=desc");
    await expectSortState(page, "Price", "descending");

    await page.reload();
    await expect(rows(page)).toHaveText(expectedRows.price.desc);
    await expectSortState(page, "Price", "descending");
  });

  test("sorts stock numerically and marks zero-stock rows", async ({ page }) => {
    await page.goto("/");

    await page.getByRole("button", { name: "Stock", exact: true }).click();
    await expect(rows(page)).toHaveText(expectedRows.stock.asc);
    await expect(page).toHaveURL("/?sort=stock&dir=asc");
    await expectSortState(page, "Stock", "ascending");

    await page.getByRole("button", { name: "Stock", exact: true }).click();
    await expect(rows(page)).toHaveText(expectedRows.stock.desc);
    await expect(page).toHaveURL("/?sort=stock&dir=desc");
    await expectSortState(page, "Stock", "descending");

    await page.goto("/?sort=stock&dir=desc");
    await expect(rows(page)).toHaveText(expectedRows.stock.desc);
    await expectSortState(page, "Stock", "descending");
    await expect(page.getByText("Out of stock")).toHaveCount(2);
    await expect(
      rows(page).filter({ hasText: "Bellows" }).getByText("Out of stock"),
    ).toBeVisible();
    await expect(
      rows(page).filter({ hasText: "Emery cloth" }).getByText("Out of stock"),
    ).toBeVisible();
  });
});
