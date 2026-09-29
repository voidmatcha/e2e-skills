import { test, expect } from './fixtures';

test('renews a loan and shows the new due date', async ({ page, memberCard }) => {
  await page.goto(`/members/${memberCard}/loans`);
  await page.getByRole('button', { name: 'Renew The Dispossessed', exact: true }).click();
  await page.waitForTimeout(1500);
  await expect(page.getByTestId('due-the-dispossessed')).toHaveText('Due 14 Oct');
});
