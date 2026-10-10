// Apache-2.0.
import {test,expect} from '@playwright/test';

test('asynchronous minimum remains one',async({page})=>{
  await page.goto('/');
  const asyncControl=page.getByRole('region',{name:'Async control',exact:true});
  const asyncValue=asyncControl.getByRole('status',{name:'Async value'});
  const cycleCompletion=asyncControl.getByRole('status',{name:'Cycle completion'});
  const asyncFewer=asyncControl.getByRole('button',{name:'Async fewer'});

  const firstRequest=page.waitForRequest(request=>request.method()==='POST'&&new URL(request.url()).pathname==='/api/fewer');
  await asyncFewer.click();
  expect((await firstRequest).postDataJSON()).toEqual({id:1});
  await expect(cycleCompletion).toHaveText('Cycle 1 complete');
  await expect(asyncFewer).toBeEnabled();

  const secondRequest=page.waitForRequest(request=>request.method()==='POST'&&new URL(request.url()).pathname==='/api/fewer');
  await asyncFewer.click();
  expect((await secondRequest).postDataJSON()).toEqual({id:2});
  await expect(cycleCompletion).toHaveText('Cycle 2 complete');
  await expect(asyncValue).toHaveText('1');
});

test('synchronous minimum remains one',async({page})=>{
  await page.goto('/');
  const syncControl=page.getByRole('region',{name:'Sync control',exact:true});
  const syncValue=syncControl.getByRole('status',{name:'Sync value'});

  await syncControl.getByRole('button',{name:'Sync fewer'}).click();

  await expect(syncValue).toHaveText('1');
});

test('disabled minimum prevents decrement',async({page})=>{
  await page.goto('/');
  const disabledControl=page.getByRole('region',{name:'Disabled control',exact:true});
  const disabledFewer=disabledControl.getByRole('button',{name:'Disabled fewer'});

  await expect(disabledFewer).toBeDisabled();
  await expect(disabledControl.getByRole('status',{name:'Disabled value'})).toHaveText('1');
});
