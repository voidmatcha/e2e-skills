// Apache-2.0.
import {test,expect} from '@playwright/test';

test.beforeEach(async({page})=>{await page.goto('/');});

test('asynchronous minimum remains one',async({page})=>{
  const asyncControl=page.getByRole('region',{name:'Async control',exact:true});
  const asyncValue=asyncControl.getByRole('status',{name:'Async value'});
  const renderCompletion=asyncControl.getByRole('status',{name:'Render completion'});
  const requestPromise=page.waitForRequest(request=>request.method()==='POST'&&new URL(request.url()).pathname==='/api/fewer');

  await expect(renderCompletion).toHaveText('Render 0 complete');
  await asyncControl.getByRole('button',{name:'Async fewer',exact:true}).click();
  const request=await requestPromise;
  expect(request.postDataJSON()).toEqual({id:1});
  await expect(renderCompletion).toHaveText('Render 1 complete');
  await expect(asyncValue).toHaveText('1');
});

test('synchronous minimum remains one',async({page})=>{
  const syncControl=page.getByRole('region',{name:'Sync control',exact:true});
  const syncValue=syncControl.getByRole('status',{name:'Sync value'});

  await syncControl.getByRole('button',{name:'Sync fewer',exact:true}).click();
  await expect(syncValue).toHaveText('1');
});

test('disabled minimum prevents decrement',async({page})=>{
  const disabledControl=page.getByRole('region',{name:'Disabled control',exact:true});
  const disabledButton=disabledControl.getByRole('button',{name:'Disabled fewer',exact:true});
  const disabledValue=disabledControl.getByRole('status',{name:'Disabled value'});

  await expect(disabledButton).toBeDisabled();
  await expect(disabledValue).toHaveText('1');
});
