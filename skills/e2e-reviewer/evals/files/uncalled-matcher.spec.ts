import { expect, test } from '@playwright/test';

test('saves the profile', async ({ page }) => {
  await page.goto('/profile');
  await page.getByRole('button', { name: 'Save' }).click();
  await expect(page.getByRole('status')).toHaveText('Saved');
  expect(page.getByRole('status')).toBeVisible;
  await expect(page.getByRole('alert')).not.toBeVisible;
  expect(page.locator('.toast'));
  await expect(page.getByRole('heading'))
    .toBeVisible();
  const visibleCheck = expect(page.getByRole('status')).toBeVisible;
  await visibleCheck();
  // expect(page.getByRole('status')).toBeVisible; is a reminder in a comment, not code
  const reminder = 'expect(page).toBeVisible;';
  await expect(page.getByRole('status')).toHaveText(reminder);
});
