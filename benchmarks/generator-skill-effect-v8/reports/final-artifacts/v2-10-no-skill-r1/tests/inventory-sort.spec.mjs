import { expect, test } from "@playwright/test";

const columns = {
  name: {
    label: "Name",
    asc: ["Anvil", "Bellows", "Chisel set", "Drawknife", "Emery cloth", "Froe"],
    desc: ["Froe", "Emery cloth", "Drawknife", "Chisel set", "Bellows", "Anvil"],
  },
  price: {
    label: "Price",
    asc: ["Emery cloth", "Froe", "Chisel set", "Bellows", "Drawknife", "Anvil"],
    desc: ["Anvil", "Drawknife", "Bellows", "Chisel set", "Froe", "Emery cloth"],
  },
  stock: {
    label: "Stock",
    asc: ["Bellows", "Emery cloth", "Drawknife", "Anvil", "Froe", "Chisel set"],
    desc: ["Chisel set", "Froe", "Anvil", "Drawknife", "Bellows", "Emery cloth"],
  },
};

const header = (page, label) =>
  page.locator("th", { has: page.getByRole("button", { name: label }) });

const rowNames = async (page) =>
  page.locator("tbody tr").evaluateAll((rows) =>
    rows.map((row) => row.cells[0].childNodes[0].textContent.trim()),
  );

const expectSortState = async (page, sortedKey, direction) => {
  for (const [key, { label }] of Object.entries(columns)) {
    await expect(header(page, label)).toHaveAttribute(
      "aria-sort",
      key === sortedKey ? direction : "none",
    );
  }
};

test("sorts inventory columns in both directions and reflects state in the URL", async ({ page }) => {
  for (const [key, column] of Object.entries(columns)) {
    await page.goto("/");

    await page.getByRole("button", { name: column.label }).click();
    await expect(page).toHaveURL(new RegExp(`\\?sort=${key}&dir=asc$`));
    await expect.poll(() => rowNames(page)).toEqual(column.asc);
    await expectSortState(page, key, "ascending");

    await page.getByRole("button", { name: column.label }).click();
    await expect(page).toHaveURL(new RegExp(`\\?sort=${key}&dir=desc$`));
    await expect.poll(() => rowNames(page)).toEqual(column.desc);
    await expectSortState(page, key, "descending");
  }
});

test("opens and reloads with URL sort state applied", async ({ page }) => {
  await page.goto("/?sort=price&dir=desc");

  await expect.poll(() => rowNames(page)).toEqual(columns.price.desc);
  await expectSortState(page, "price", "descending");

  await page.reload();

  await expect(page).toHaveURL(/\/\?sort=price&dir=desc$/);
  await expect.poll(() => rowNames(page)).toEqual(columns.price.desc);
  await expectSortState(page, "price", "descending");
});

test("marks zero-stock rows with an out-of-stock badge", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByText("Out of stock")).toHaveCount(2);
  await expect(
    page.getByRole("row", { name: /Bellows .*Out of stock.*0/ }),
  ).toBeVisible();
  await expect(
    page.getByRole("row", { name: /Emery cloth .*Out of stock.*0/ }),
  ).toBeVisible();
});
