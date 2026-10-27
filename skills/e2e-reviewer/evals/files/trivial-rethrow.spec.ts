// SPDX-License-Identifier: Apache-2.0
import { test } from '@playwright/test';
async function preserve(action) {
  try { await action(); } catch (error) { throw error; }
}
async function swallow(action) {
  try { await action(); } catch (error) {}
}
test('helpers', async () => { await preserve(async () => 42); await swallow(async () => 42); });
