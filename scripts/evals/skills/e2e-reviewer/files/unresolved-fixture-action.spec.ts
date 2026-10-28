// SPDX-License-Identifier: Apache-2.0
import { test } from '@project/fixture';

test('navigation', async ({ page }) => {
  page.goto('/settings');
  await page.goto('/account');
});
