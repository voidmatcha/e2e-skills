import { expect, expect as verify, test } from '@playwright/test'; import * as pw from '@playwright/test'

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

test('nearest binding controls Locator provenance', async ({ page }) => {
  const status = page.locator('#status')
  {
    const status = { ready: true }
    await expect(status).toBeTruthy()
  }
  await expect(status).toBeTruthy()
})

test('long aliased retry callback is not one-shot', async ({ page }) => {
  await verify(async () => {
    // retry padding 01
    // retry padding 02
    // retry padding 03
    // retry padding 04
    // retry padding 05
    // retry padding 06
    // retry padding 07
    // retry padding 08
    // retry padding 09
    // retry padding 10
    // retry padding 11
    // retry padding 12
    // retry padding 13
    // retry padding 14
    // retry padding 15
    // retry padding 16
    // retry padding 17
    // retry padding 18
    // retry padding 19
    // retry padding 20
    // retry padding 21
    // retry padding 22
    // retry padding 23
    // retry padding 24
    // retry padding 25
    // retry padding 26
    // retry padding 27
    // retry padding 28
    // retry padding 29
    // retry padding 30
    // retry padding 31
    // retry padding 32
    // retry padding 33
    // retry padding 34
    // retry padding 35
    // retry padding 36
    // retry padding 37
    // retry padding 38
    // retry padding 39
    // retry padding 40
    // retry padding 41
    expect(page.url()).toBe('/ready')
    expect(await page.locator('.ready').innerText()).toBe('Ready')
  }).toPass()
})

test('namespace retry callback is not one-shot', async ({ page }) => {
  await pw.expect(async () => {
    expect(page.url()).toBe('/ready')
  }).toPass()
})

test('destructured binding shadows Locator provenance', async ({ page }) => {
  const status = page.locator('#status')
  {
    const { status } = { status: { ready: true } }
    await expect(status).toBeTruthy()
  }
  await expect(status).toBeTruthy()
})

test('typed function parameter shadows Locator provenance', async ({ page }) => {
  const status = page.locator('#status')
  async function probe(status: { ready: boolean }) {
    await expect(status).toBeTruthy()
  }
  await probe({ ready: true })
  await expect(status).toBeTruthy()
})

test('typed method parameter shadows Locator provenance', async ({ page }) => {
  const status = page.locator('#status')
  const object = {
    async probe(status: { ready: boolean }) {
      await expect(status).toBeTruthy()
    },
  }
  await object.probe({ ready: true })
  await expect(status).toBeTruthy()
})
