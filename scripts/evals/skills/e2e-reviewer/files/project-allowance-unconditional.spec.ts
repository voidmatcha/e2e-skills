import { test, expect } from '@playwright/test';

const isProductionProject = (name: string): boolean => name.includes('production');
const extractKey = (context: string): string | null => context.match(/key: "([^"]+)"/)?.[1] ?? null;

test('keeps the selected key stable through reorder', async ({ page }, testInfo) => {
  const target = page.getByTestId('reorder-key-target');
  const keyBefore = extractKey((await target.getAttribute('data-context')) ?? '');
  await page.getByTestId('reorder-list-button').click();
  const contextAfter = (await target.getAttribute('data-context')) ?? '';
  if (!isProductionProject(testInfo.project.name)) {
    expect(keyBefore).not.toBeNull();
  }
  if (keyBefore) expect(keyBefore).toBe('target');
  expect(extractKey(contextAfter)).toBe('target');
});
