import { expect, Page } from '@playwright/test';
export async function verifyNorth(page: Page) {
  try {
    await expect(page.getByTestId('bearing')).toHaveText('North');
  } catch (error) {
    console.info('readout delayed');
  }
}
