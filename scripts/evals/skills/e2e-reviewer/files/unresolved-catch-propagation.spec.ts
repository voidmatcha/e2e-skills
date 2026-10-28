// SPDX-License-Identifier: Apache-2.0
import { test } from '@playwright/test';
async function optionalAction(action) {
  try { const result = await action(); return result; } catch (error) {}
}
async function requiredAction(action) {
  try { return await action(); } catch (error) { console.error(error); throw error; }
}
test('helpers', async () => {
  await optionalAction(async () => 42);
  await requiredAction(async () => 42);
});
