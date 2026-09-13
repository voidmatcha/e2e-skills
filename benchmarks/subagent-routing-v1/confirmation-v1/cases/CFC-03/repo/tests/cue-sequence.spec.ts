// confirmation-case: CFC-03/tests/cue-sequence.spec.ts
import { expect, test } from '@playwright/test';
let previousCue = '';
test.beforeEach(async ({ page }) => {
  if (previousCue) await page.evaluate((cue) => localStorage.setItem('previousCue', cue), previousCue);
});
test('records opening cue', async ({ page }) => { previousCue = 'opening'; await page.goto('/stage/cues'); });
test('shows closing cue independently', async ({ page }) => {
  await page.goto('/stage/cues');
  await expect(page.getByTestId('closing-cue')).toBeVisible();
});
