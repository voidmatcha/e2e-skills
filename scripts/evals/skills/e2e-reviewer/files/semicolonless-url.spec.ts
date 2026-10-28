// SPDX-License-Identifier: Apache-2.0
import { expect, test } from '@playwright/test'
test('URL assertions', async ({ page }) => {
  await expect(async () => {
    expect(page.url()).toBe('/ready')
  }).toPass()
  const pageLike = { url: () => '/ready' }
  expect(pageLike.url()).toBe('/ready')
  expect(page.url()).toBe('/ready')
  expect(page.url()).toEqual('/ready')
})
