import { expect, test } from "@playwright/test";

const ORDERS = {
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
const KEYS = Object.keys(ORDERS);
const ARIA = { asc: "ascending", desc: "descending" };

const header = (page, key) => page.locator("th", { has: page.locator(`#iv-sort-${key}`) });
const sortButton = (page, key) => page.locator(`#iv-sort-${key}`);

// Product names in row order, without the "Out of stock" badge text.
const names = (page) =>
  page.locator("#iv-rows tr td:first-child").evaluateAll((cells) =>
    cells.map((td) => td.firstChild.textContent.trim()),
  );

async function expectSort(page, key, dir) {
  await expect.poll(() => names(page)).toEqual(ORDERS[key][dir]);
  for (const other of KEYS) {
    await expect(header(page, other)).toHaveAttribute(
      "aria-sort",
      other === key ? ARIA[dir] : "none",
    );
  }
  await expect(page).toHaveURL((url) => url.search === `?sort=${key}&dir=${dir}`);
}

test("starts unsorted with every header at aria-sort none", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("#iv-rows tr")).toHaveCount(6);
  for (const key of KEYS) await expect(header(page, key)).toHaveAttribute("aria-sort", "none");
  expect(new URL(page.url()).search).toBe("");
});

for (const key of KEYS) {
  test(`clicking ${key} sorts ascending, then descending`, async ({ page }) => {
    await page.goto("/");
    await sortButton(page, key).click();
    await expectSort(page, key, "asc");
    await sortButton(page, key).click();
    await expectSort(page, key, "desc");
    await sortButton(page, key).click();
    await expectSort(page, key, "asc");
  });
}

test("switching columns starts ascending and resets the other headers", async ({ page }) => {
  await page.goto("/");
  await sortButton(page, "price").click();
  await sortButton(page, "price").click();
  await expectSort(page, "price", "desc");
  await sortButton(page, "stock").click();
  await expectSort(page, "stock", "asc");
});

test("price sorts numerically, not as text", async ({ page }) => {
  await page.goto("/");
  await sortButton(page, "price").click();
  const prices = await page.locator("#iv-rows tr td:nth-child(2)").allTextContents();
  expect(prices).toEqual(["$7.00", "$9.50", "$15.00", "$42.00", "$68.00", "$120.00"]);
});

test("stock sorts numerically, not as text", async ({ page }) => {
  await page.goto("/");
  await sortButton(page, "stock").click();
  await sortButton(page, "stock").click();
  const stock = await page.locator("#iv-rows tr td:nth-child(3)").allTextContents();
  expect(stock).toEqual(["14", "6", "2", "1", "0", "0"]);
});

for (const key of KEYS) {
  for (const dir of ["asc", "desc"]) {
    test(`opening ?sort=${key}&dir=${dir} directly shows that sort`, async ({ page }) => {
      await page.goto(`/?sort=${key}&dir=${dir}`);
      await expectSort(page, key, dir);
    });
  }
}

test("reloading keeps the sort and header state", async ({ page }) => {
  await page.goto("/");
  await sortButton(page, "price").click();
  await sortButton(page, "price").click();
  await expectSort(page, "price", "desc");
  await page.reload();
  await expectSort(page, "price", "desc");
});

test("rows with zero stock show an Out of stock badge, others do not", async ({ page }) => {
  await page.goto("/");
  const rows = page.locator("#iv-rows tr");
  await expect(rows).toHaveCount(6);
  await expect(page.getByText("Out of stock")).toHaveCount(2);
  for (const name of ["Bellows", "Emery cloth"]) {
    await expect(rows.filter({ hasText: name }).getByText("Out of stock")).toBeVisible();
  }
  for (const name of ["Anvil", "Chisel set", "Drawknife", "Froe"]) {
    await expect(rows.filter({ hasText: name }).getByText("Out of stock")).toHaveCount(0);
  }
});

test("the badge follows its row when sorted", async ({ page }) => {
  await page.goto("/?sort=stock&dir=asc");
  const rows = page.locator("#iv-rows tr");
  await expect(rows.nth(0)).toContainText("Out of stock");
  await expect(rows.nth(1)).toContainText("Out of stock");
  await expect(rows.nth(2)).not.toContainText("Out of stock");
});
