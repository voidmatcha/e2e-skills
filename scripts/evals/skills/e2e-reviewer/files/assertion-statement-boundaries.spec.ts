// SPDX-License-Identifier: Apache-2.0
import { expect, test } from '@playwright/test'

test('keeps each assertion subject with its own matcher', async ({ page }) => {
  const popup = page.locator('.popup')
  await expect(popup).toBeVisible()
  const box = await popup.boundingBox()
  expect(box).not.toBeNull()
  await expect(page.locator('.heading')).toBeVisible()
  expect(await page.locator('.heading').boundingBox()).not.toBeNull()
  await expect(popup)
    .toBeVisible()
  expect(box).not.toBeNull()
  expect(popup).not.toBeNull()
  expect(
    popup,
  ).not.toBeNull()
  expect(page.locator('.direct')).toBeTruthy()
})
