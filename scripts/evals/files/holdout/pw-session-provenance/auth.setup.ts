import { expect, test as setup } from '@playwright/test';

setup('creates a generated authenticated session', async ({ context, page }) => {
  const sessionToken = process.env.E2E_SESSION_TOKEN;
  expect(sessionToken).toBeTruthy();

  await context.addCookies([
    {
      name: 'session',
      value: sessionToken as string,
      domain: 'example.test',
      path: '/',
      httpOnly: true,
      secure: true,
      sameSite: 'Lax',
    },
  ]);
  await page.goto('/account');
  await context.storageState({ path: 'playwright/.auth/generated.json' });
});
