import { expect, test } from '@playwright/test';

const steps = [
  'Ordered',
  'Packed',
  'Shipped',
  'Out for delivery',
  'Delivered',
];

async function expectTrackingState(page, currentIndex) {
  await expect(
    page.getByText(`Step ${currentIndex + 1} of 5: ${steps[currentIndex]}`)
  ).toBeVisible();

  for (const [index, step] of steps.entries()) {
    const item = page.getByRole('listitem').filter({ hasText: step });

    await expect(item).toBeVisible();

    if (index < currentIndex) {
      await expect(item).toContainText('Done');
      await expect(item).not.toContainText('Current');
      await expect(item).not.toContainText('Upcoming');
    } else if (index === currentIndex) {
      await expect(item).toContainText('Current');
      await expect(item).not.toContainText('Done');
      await expect(item).not.toContainText('Upcoming');
    } else {
      await expect(item).toContainText('Upcoming');
      await expect(item).not.toContainText('Done');
      await expect(item).not.toContainText('Current');
    }
  }
}

test.describe.serial('order tracking', () => {
  test.beforeEach(async ({ request }) => {
    await expect((await request.post('/api/reset')).ok()).toBeTruthy();
  });

  test('advances through the timeline and persists progress after reload', async ({ page }) => {
    await page.goto('/');

    for (let index = 0; index < steps.length; index += 1) {
      await expectTrackingState(page, index);
      await expect(page.getByRole('button', { name: 'Cancel order' })).toHaveCount(
        index < 2 ? 1 : 0
      );

      await page.reload();
      await expectTrackingState(page, index);
      await expect(page.getByRole('button', { name: 'Cancel order' })).toHaveCount(
        index < 2 ? 1 : 0
      );

      if (index < steps.length - 1) {
        await page.getByRole('button', { name: 'Advance' }).click();
      }
    }
  });

  test('allows cancellation before shipping and persists it after reload', async ({ page }) => {
    await page.goto('/');

    await expectTrackingState(page, 0);
    await expect(page.getByRole('button', { name: 'Cancel order' })).toBeVisible();

    await page.getByRole('button', { name: 'Cancel order' }).click();

    await expect(page.getByText('Order cancelled', { exact: true })).toBeVisible();
    await expect(page.getByText('Cancelled', { exact: true })).toBeVisible();
    await expect(page.getByText(/estimated delivery/i)).toBeHidden();

    for (const step of steps) {
      const item = page.getByRole('listitem').filter({ hasText: step });
      await expect(item).not.toContainText('Current');
    }

    await page.reload();

    await expect(page.getByText('Order cancelled', { exact: true })).toBeVisible();
    await expect(page.getByText('Cancelled', { exact: true })).toBeVisible();
    await expect(page.getByText(/estimated delivery/i)).toBeHidden();

    for (const step of steps) {
      const item = page.getByRole('listitem').filter({ hasText: step });
      await expect(item).not.toContainText('Current');
    }
  });
});
