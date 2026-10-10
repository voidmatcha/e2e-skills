// Apache-2.0.
import {test,expect} from '@playwright/test';

test.beforeEach(async({page})=>{await page.goto('/');});

test('asynchronous minimum remains one after a second decrement',async({page})=>{
  const asyncControl=page.getByRole('region',{name:'Async control',exact:true});
  const asyncFewer=asyncControl.getByRole('button',{name:'Async fewer'});
  const asyncValue=asyncControl.getByRole('status',{name:'Async value'});
  const cycleCompletion=asyncControl.getByRole('status',{name:'Cycle completion'});

  await asyncFewer.click();
  await expect(cycleCompletion).toHaveText('Cycle 1 complete');
  await expect(asyncFewer).toBeEnabled();

  const asyncRequest=page.waitForRequest(request=>request.method()==='POST'&&new URL(request.url()).pathname==='/api/fewer');
  await asyncFewer.click();
  const request=await asyncRequest;
  expect(request.postDataJSON()).toEqual({id:2});
  await expect(cycleCompletion).toHaveText('Cycle 2 complete');
  await expect(asyncValue).toHaveText('1');
});

test('synchronous minimum remains one after decrement',async({page})=>{
  const syncControl=page.getByRole('region',{name:'Sync control',exact:true});
  const syncFewer=syncControl.getByRole('button',{name:'Sync fewer'});
  const syncValue=syncControl.getByRole('status',{name:'Sync value'});

  await syncFewer.click();
  await expect(syncValue).toHaveText('1');
});

test('disabled minimum prevents decrement',async({page})=>{
  const disabledControl=page.getByRole('region',{name:'Disabled control',exact:true});
  const disabledFewer=disabledControl.getByRole('button',{name:'Disabled fewer'});
  const disabledValue=disabledControl.getByRole('status',{name:'Disabled value'});

  await expect(disabledFewer).toBeDisabled();
  await expect(disabledValue).toHaveText('1');
});
