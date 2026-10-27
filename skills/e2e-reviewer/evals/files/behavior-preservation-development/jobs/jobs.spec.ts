// SPDX-License-Identifier: Apache-2.0
import { test, expect } from '@playwright/test';
import { JobsPage } from './jobs-page';
test('job a completes', async ({ page }) => {
  await page.goto('/jobs');
  const jobs = new JobsPage(page);
  await jobs.start();
  await expect(jobs.completion()).toBeVisible();
});
