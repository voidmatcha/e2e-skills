// confirmation-case: CFV-03/tests/cue-panel.spec.ts
import { test, type Page } from '@playwright/test';

async function cuePanelIsReady(page: Page): Promise<boolean> {
  return page.getByTestId('cue-panel-ready').isVisible();
}

test('opens the stage cue panel', async ({ page }) => {
  await page.goto('/stage/cues');
  await cuePanelIsReady(page);
});
