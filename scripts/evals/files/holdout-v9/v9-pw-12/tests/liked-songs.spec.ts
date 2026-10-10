import { test, expect } from '@playwright/test';
import likedSongs from './fixtures/liked-songs.json';

test('lists both liked songs on the Liked tab', async ({ page }) => {
  await page.route('**/api/me/songs?tab=liked', (route) => route.fulfill({ json: likedSongs }));
  await page.goto('/library?tab=liked');
  await expect(page.getByTestId('song-card')).toHaveCount(2);
});
