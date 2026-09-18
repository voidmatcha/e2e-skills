// SPDX-License-Identifier: Apache-2.0
import { expect, test } from '@playwright/test';

test('main is visible: sole swallowed oracle', async ({ page }) => {
  await expect(page.getByRole('main')).toBeVisible().catch(() => {});
});

test('main is visible: multiline swallowed oracle', async ({ page }) => {
  await expect(page.getByRole('main'))
    .toBeVisible()
    .catch(() => {});
});

test('independent assertion on same line', async ({ page }) => {
  await expect(page.getByRole('main')).toBeVisible(); await page.title().catch(() => {});
});

test('independent assertion after semicolonless catch', async ({ page }) => {
  await page.title().catch(() => {})
  await expect(page.getByRole('main')).toBeVisible();
});

test('custom matcher-shaped method', async ({ page }) => {
  const exporter = { toBuffer: async () => new Uint8Array() };
  await exporter.toBuffer().catch(() => {});
  await expect(page.getByRole('main')).toBeVisible();
});

test('shadowed expect helper', async () => {
  const expect = async () => {};
  await expect().catch(() => {});
});

test('soft failure stays recorded', async ({ page }) => {
  await expect.soft(page.getByRole('main')).toBeVisible().catch(() => {});
});

test('synchronous failure precedes catch', () => {
  expect(1).toBe(2).catch(() => {});
});

test('main remains absent: later assertion fails', async ({ page }) => {
  await expect(page.getByRole('main')).toBeVisible().catch(() => {});
  await expect(page.getByRole('main')).toBeVisible();
});

test('finally prevents passing', async ({ page }) => {
  try {
    await expect(page.getByRole('main')).toBeVisible().catch(() => {});
  } finally { throw new Error('unconditional failure'); }
});

test('main is visible and heading says Welcome', async ({ page }) => {
  await expect(page.getByRole('main')).toBeVisible().catch(() => {});
  await expect(page.getByRole('heading')).toHaveText('Welcome');
});
