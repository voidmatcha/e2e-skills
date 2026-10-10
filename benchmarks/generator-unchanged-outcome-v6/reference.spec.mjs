// Apache-2.0. Excluded from generation workspaces.
import { test, expect } from '@playwright/test';
test.beforeEach(async ({page}) => {
  await page.goto('/');
  if(await page.locator('main[data-case="repeated-ready"]').count()) {
    await page.getByRole('button', {name:'Async fewer'}).click();
    await expect(page.getByRole('status', {name:'Render completion'})).toHaveText('Render 1 complete');
  }
});
test('stale immediate assertion', async ({page}) => {
  await page.getByRole('button', {name:'Async fewer'}).click();
  await expect(page.getByRole('status', {name:'Completion', exact:true})).toHaveText('Ready');
  await expect(page.getByRole('status', {name:'Async value', exact:true})).toHaveText('1');
});
test('request-only assertion', async ({page}) => {
  const response = page.waitForResponse(r => r.url().endsWith('/api/fewer') && r.request().method() === 'POST');
  await page.getByRole('button', {name:'Async fewer'}).click();
  await response;
  await expect(page.getByRole('status', {name:'Async value', exact:true})).toHaveText('1');
});
test('render completion assertion', async ({page}) => {
  const repeated = await page.locator('main[data-case="repeated-ready"]').count();
  await expect(page.getByRole('status', {name:'Render completion'})).toHaveText(repeated ? 'Render 1 complete' : 'Render 0 complete');
  await page.getByRole('button', {name:'Async fewer'}).click();
  await expect(page.getByRole('status', {name:'Render completion'})).toHaveText(repeated ? 'Render 2 complete' : 'Render 1 complete');
  await expect(page.getByRole('status', {name:'Async value', exact:true})).toHaveText('1');
});
test('synchronous guard', async ({page}) => {
  await page.getByRole('button', {name:'Sync fewer',exact:true}).click();
  await expect(page.getByRole('status', {name:'Sync value',exact:true})).toHaveText('1');
});
test('disabled guard', async ({page}) => {
  await expect(page.getByRole('button', {name:'Disabled fewer'})).toBeDisabled();
  await expect(page.getByRole('status', {name:'Disabled value'})).toHaveText('1');
});



