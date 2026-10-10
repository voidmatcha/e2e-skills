// Apache-2.0.
import {test,expect} from '@playwright/test';

test.beforeEach(async({page})=>{await page.goto('/');});

test('asynchronous minimum remains one',async({page})=>{
  const asyncControl=page.getByRole('region',{name:'Async control',exact:true});
  const asyncValue=asyncControl.getByRole('status',{name:'Async value'});
  const cycleCompletion=asyncControl.getByRole('status',{name:'Cycle completion'});
  const asyncFewer=asyncControl.getByRole('button',{name:'Async fewer'});

  await asyncFewer.click();
  await expect(cycleCompletion).toHaveText('Cycle 1 complete');
  await expect(asyncFewer).toBeEnabled();

  const secondRequestPromise=page.waitForRequest(request=>request.method()==='POST'&&new URL(request.url()).pathname==='/api/fewer');
  await asyncFewer.click();
  const secondRequest=await secondRequestPromise;
  expect(secondRequest.postDataJSON()).toEqual({id:2});
  await expect(cycleCompletion).toHaveText('Cycle 2 complete');
  await expect(asyncValue).toHaveText('1');
});

test('synchronous minimum remains one',async({page})=>{
  const syncControl=page.getByRole('region',{name:'Sync control',exact:true});

  await syncControl.getByRole('button',{name:'Sync fewer'}).click();

  await expect(syncControl.getByRole('status',{name:'Sync value'})).toHaveText('1');
});

test('disabled minimum prevents decrement',async({page})=>{
  const disabledControl=page.getByRole('region',{name:'Disabled control',exact:true});
  const disabledFewer=disabledControl.getByRole('button',{name:'Disabled fewer'});

  await expect(disabledFewer).toBeDisabled();
  await expect(disabledControl.getByRole('status',{name:'Disabled value'})).toHaveText('1');
});
