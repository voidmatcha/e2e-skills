import { expect, test } from '@playwright/test';

test('selects a region with the legacy page API', async ({ page }) => {
  await page.goto('/preferences');
  await page.selectOption('#region', 'KR');
  await expect(page.locator('#region')).toHaveValue('KR');
});

test('uses the locator API for timezone', async ({ page }) => {
  await page.goto('/preferences');
  await page.locator('#timezone').selectOption('Asia/Seoul');
  await expect(page.locator('#timezone')).toHaveValue('Asia/Seoul');
});

test('edits a profile through a soft-gated form', async ({ page }) => {
  await page.goto('/profile');
  const profileForm = page.getByTestId('profile-form');
  await expect.soft(profileForm).toBeVisible();
  await profileForm.getByLabel('Display name').fill('Mina Kim');
  await profileForm.getByRole('button', { name: 'Save' }).click();
  await expect(page.getByRole('status')).toHaveText('Saved');
});

test('collects independent terminal details after a hard gate', async ({ page }) => {
  await page.goto('/profile');
  await expect(page).toHaveURL('/profile');
  await expect(page.getByRole('main')).toBeVisible();
  await expect.soft(page.getByTestId('display-name')).toHaveText('Mina');
  await expect.soft(page.getByTestId('locale')).toHaveText('ko-KR');
});
