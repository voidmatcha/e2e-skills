// SPDX-License-Identifier: Apache-2.0
import { expect } from '@playwright/test';
export async function expectSettingsSaved(page) {
  await expect(page.getByTestId('save-state')).toHaveText('Saved');
}
