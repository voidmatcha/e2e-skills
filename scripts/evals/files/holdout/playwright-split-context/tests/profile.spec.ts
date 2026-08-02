import { expect, test } from '@playwright/test';
import { ProfilePage } from '../pages/profile-page';
import { FeatureFlags } from '../support/feature-flags';

test('shows the profile heading', async ({ page }) => {
  const profile = new ProfilePage(page);
  const flags = new FeatureFlags();
  await page.goto('/profile');

  if (await profile.savedToast.isVisible()) {
    await expect(profile.savedToast).toBeHidden();
  }

  if (await profile.advancedToggle.isVisible()) {
    await profile.advancedToggle.click();
  }

  expect(profile.nameInput).toBeTruthy();
  expect(await flags.isEnabled('profile-v2')).toBe(true);
  await expect(profile.heading).toHaveText('Profile');
});
