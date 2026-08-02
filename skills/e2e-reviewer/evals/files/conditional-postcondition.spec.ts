import { expect, test } from '@playwright/test';

test('saves the document', async ({ page }) => {
  await page.goto('/editor/doc-2');
  await page.getByRole('button', { name: 'Save' }).click();
  if (await page.getByRole('status').isVisible()) {
    await expect(page.getByRole('status')).toContainText('Saved');
  }
  await expect(page.getByTestId('saved-document')).toHaveAttribute('data-id', 'doc-2');
});
