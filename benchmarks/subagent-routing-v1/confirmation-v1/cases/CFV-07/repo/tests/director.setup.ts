// confirmation-case: CFV-07/tests/director.setup.ts
import { expect, test as setup } from '@playwright/test';
setup('director auth', async ({ page }) => {
  await page.goto('/login');
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page.getByTestId('role')).toHaveText('technical-director');
  await page.context().storageState({ path: '.auth/director.json' });
});
