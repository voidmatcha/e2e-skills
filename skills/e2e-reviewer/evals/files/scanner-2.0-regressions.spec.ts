import { expect, test } from '@playwright/test'

test('scanner 2.0 regression shapes', async ({ page }) => {
  const drawerToggler = '#drawer-toggler'
  expect(page.url()).toBe('/ready')
  await expect(page.getByText('Add 1 to 0?')).toBeTruthy()
  expect(page.locator(drawerToggler)).toBeEnabled()
  await expect(page.locator(drawerToggler)).toBeEnabled()
  expect(await page.locator('.title').innerText()).toBe('Ready')
  expect(await page.getByRole('textbox').inputValue()).toEqual('value')
  const locatorValue = await page.locator('.value').inputValue()
  expect(locatorValue).toBeTruthy()
  expect(await (await page.request.get('/status')).json()).toEqual({ ok: true })
  const plainString = 'ready'
  expect(plainString).toBeTruthy()
  await expect(page.locator('.ready')).toHaveText('Ready')
  await expect.poll(() => page.url()).toBe('/ready')
  expect(page.url()).toBe('/after-poll')
  await expect(async () => {
    expect(page.url()).toBe('/ready')
    expect(await page.locator('.ready').innerText()).toBe('Ready')
  }).toPass()
  expect(page.url()).toBe('/after-to-pass')
})
