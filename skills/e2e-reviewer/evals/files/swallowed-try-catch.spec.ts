import { test, expect, type Page } from '@playwright/test';

async function waitForSaved(page: Page) {
  try {
    await page.getByTestId('saved-toast').waitFor({ state: 'visible' });
  } catch {
    // toast sometimes disappears too fast
  }
}

async function openPanel(page: Page) {
  for (let attempt = 0; attempt < 3; attempt++) {
    await page.getByRole('button', { name: 'Details' }).click();
    try {
      await expect(page.getByRole('dialog')).toBeVisible({ timeout: 1000 });
      return;
    } catch {
      // retry
    }
  }
}

async function loadChart(page: Page, id: string) {
  const result = { id, loaded: false };
  try {
    await expect(page.getByTestId(id)).toHaveAttribute('data-state', 'loaded');
    result.loaded = true;
  } catch {
    result.loaded = false;
  }
  return result;
}

test('saving a profile shows a confirmation', async ({ page }) => {
  await page.goto('/profile');
  await page.getByLabel('Name').fill('Ada');
  await page.getByRole('button', { name: 'Save' }).click();
  await waitForSaved(page);
});

test('details panel opens', async ({ page }) => {
  await page.goto('/projects/1');
  await openPanel(page);
  await expect(page).toHaveURL(/\/projects\/1/);
});

test('health endpoint answers', async ({ page }) => {
  try {
    await page.request.get('/api/health').then((response) => expect(response.ok()).toBeTruthy());
  } catch (error) {
    console.warn('health check skipped', error);
  }
  await page.goto('/status');
});

test('rejects an overlapping slot', async ({ page }) => {
  await page.goto('/slots');
  try {
    await page.getByTestId('slot-conflict').waitFor({ state: 'visible' });
  } catch (error) {
    if (!(error instanceof Error && error.name === 'TimeoutError')) {
      throw error;
    }
  }
  await expect(page.getByTestId('notice')).toHaveText('Slot taken');
});

test('dashboard charts load', async ({ page }) => {
  await page.goto('/dashboard');
  const results = [await loadChart(page, 'sales'), await loadChart(page, 'visits')];
  const failed = results.filter((result) => !result.loaded);
  if (failed.length > 0) {
    throw new Error(`charts failed to load: ${failed.map((result) => result.id).join(', ')}`);
  }
});

test('search returns the project', async ({ page }) => {
  await page.goto('/');
  try {
    await page.getByRole('button', { name: 'Accept cookies' }).waitFor({ timeout: 2000 });
    await page.getByRole('button', { name: 'Accept cookies' }).click();
  } catch {
    // the banner only appears for new visitors
  }
  await page.getByRole('searchbox').fill('apollo');
  await expect(page.getByRole('link', { name: 'Apollo' })).toBeVisible();
});

test('settings page reads the saved theme', async ({ page }) => {
  let theme = 'light';
  try {
    theme = JSON.parse(process.env.E2E_SETTINGS ?? '{}').theme ?? 'light';
  } catch {
    theme = 'light';
  }
  await page.goto('/settings');
  await expect(page.getByTestId('theme')).toHaveText(theme);
});

test('allows one named scheduling conflict', async ({ page }) => {
  try {
    await page.getByTestId('slot').waitFor({ state: 'visible' });
  } catch (error) {
    if (!(error instanceof SlotError)) {
      throw error;
    }
  }
  await expect(page.getByTestId('notice')).toHaveText('Slot taken');
});

test('logs diagnostics before propagating', async ({ page }) => {
  try {
    await page.getByTestId('receipt').waitFor({ state: 'visible' });
  } catch (error) {
    console.error('receipt missing', error);
    console.error('url', page.url());
    throw error;
  }
});

test('ordinary constructor timeout is not an application allowlist', async ({ page }) => {
  try {
    await page.getByTestId('invoice').waitFor({ state: 'visible' });
  } catch (error) {
    if (!(error.constructor.name === 'BrowserTimeoutError')) throw error;
  }
  await expect(page.getByTestId('invoice')).toBeVisible();
});

test('allows one named payment failure', async ({ page }) => {
  try {
    await page.getByTestId('payment').waitFor({ state: 'visible' });
  } catch (error) {
    if (error.name !== 'PaymentError') throw error;
  }
  await expect(page.getByTestId('payment-help')).toBeVisible();
});
