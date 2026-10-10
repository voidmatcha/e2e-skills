import { expect, test } from "@playwright/test";

const columns = {
  name: "Name",
  price: "Price",
  stock: "Stock",
};

const expected = {
  name: {
    asc: ["Anvil", "Bellows", "Chisel set", "Drawknife", "Emery cloth", "Froe"],
    desc: ["Froe", "Emery cloth", "Drawknife", "Chisel set", "Bellows", "Anvil"],
  },
  price: {
    asc: ["Emery cloth", "Froe", "Chisel set", "Bellows", "Drawknife", "Anvil"],
    desc: ["Anvil", "Drawknife", "Bellows", "Chisel set", "Froe", "Emery cloth"],
  },
  stock: {
    asc: ["Bellows", "Emery cloth", "Drawknife", "Anvil", "Froe", "Chisel set"],
    desc: ["Chisel set", "Froe", "Anvil", "Drawknife", "Bellows", "Emery cloth"],
  },
};

const names = (page) =>
  page.locator("tbody tr td:first-child").evaluateAll((cells) =>
    cells.map((cell) => cell.childNodes[0].textContent.trim()),
  );

const header = (page, key) => page.getByRole("columnheader", { name: columns[key] });
const sortButton = (page, key) => page.getByRole("button", { name: columns[key] });

async function expectSortState(page, sortedKey, direction) {
  await expect(header(page, sortedKey)).toHaveAttribute("aria-sort", direction);

  for (const key of Object.keys(columns)) {
    if (key !== sortedKey) {
      await expect(header(page, key)).toHaveAttribute("aria-sort", "none");
    }
  }
}

for (const [key, label] of Object.entries(columns)) {
  test(`${label} header sorts ascending and descending`, async ({ page }) => {
    await page.goto("/");

    await sortButton(page, key).click();
    await expect(names(page)).resolves.toEqual(expected[key].asc);
    await expect(page).toHaveURL(`/?sort=${key}&dir=asc`);
    await expectSortState(page, key, "ascending");

    await sortButton(page, key).click();
    await expect(names(page)).resolves.toEqual(expected[key].desc);
    await expect(page).toHaveURL(`/?sort=${key}&dir=desc`);
    await expectSortState(page, key, "descending");
  });
}

test("deep-linked sort survives reload with matching header state", async ({ page }) => {
  await page.goto("/?sort=price&dir=desc");

  await expect(names(page)).resolves.toEqual(expected.price.desc);
  await expectSortState(page, "price", "descending");

  await page.reload();

  await expect(names(page)).resolves.toEqual(expected.price.desc);
  await expect(page).toHaveURL("/?sort=price&dir=desc");
  await expectSortState(page, "price", "descending");
});

test("zero-stock rows show an out-of-stock badge", async ({ page }) => {
  await page.goto("/");

  await expect(page.locator("tbody tr", { hasText: "Bellows" }).getByText("Out of stock")).toBeVisible();
  await expect(page.locator("tbody tr", { hasText: "Emery cloth" }).getByText("Out of stock")).toBeVisible();
  await expect(page.getByText("Out of stock")).toHaveCount(2);
});
