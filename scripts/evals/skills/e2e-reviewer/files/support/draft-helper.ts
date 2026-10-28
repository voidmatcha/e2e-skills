import { type Page } from '@playwright/test';

export async function saveDraft(
  page: Page,
  invoiceId: string,
  total: string,
): Promise<void> {
  await page.getByTestId(`invoice-row-${invoiceId}`).click();
  await page.getByTestId('draft-total-input').fill(total);
  await page.getByRole('button', { name: 'Save draft', exact: true }).click();
  // BAD (#3) — the save-confirmation gate is swallowed, so the caller proceeds
  // as if the draft persisted. The spec then asserts on a total the client
  // rendered optimistically, and passes even when the save failed.
  try {
    await page.getByTestId('draft-saved-badge').waitFor({ state: 'visible', timeout: 5000 });
  } catch (error) {
    console.warn(`draft save was not confirmed for ${invoiceId}`, error);
  }
}
