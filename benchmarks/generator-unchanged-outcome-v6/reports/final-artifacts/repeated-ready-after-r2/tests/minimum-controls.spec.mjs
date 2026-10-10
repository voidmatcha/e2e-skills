// Apache-2.0.
import {test,expect} from '@playwright/test';

test.beforeEach(async({page})=>{await page.goto('/');});

test('asynchronous minimum remains one',async({page})=>{
  const asyncControl=page.getByRole('region',{name:'Async control',exact:true});
  const asyncValue=asyncControl.getByRole('status',{name:'Async value'});
  const renderCompletion=asyncControl.getByRole('status',{name:'Render completion'});
  const asyncFewer=asyncControl.getByRole('button',{name:'Async fewer'});

  await asyncFewer.click();
  await expect(renderCompletion).toHaveText('Render 1 complete');

  const requestPromise=page.waitForRequest(request=>request.method()==='POST'&&new URL(request.url()).pathname==='/api/fewer');
  await asyncFewer.click();
  const request=await requestPromise;
  expect(JSON.parse(request.postData()??'{}')).toEqual({id:2});
  await expect(renderCompletion).toHaveText('Render 2 complete');
  await expect(asyncValue).toHaveText('1');
});

test('synchronous minimum remains one',async({page})=>{
  const syncControl=page.getByRole('region',{name:'Sync control',exact:true});
  const syncValue=syncControl.getByRole('status',{name:'Sync value'});

  await syncControl.getByRole('button',{name:'Sync fewer'}).click();
  await expect(syncValue).toHaveText('1');
});

test('disabled minimum prevents decrement',async({page})=>{
  const disabledControl=page.getByRole('region',{name:'Disabled control',exact:true});
  const disabledValue=disabledControl.getByRole('status',{name:'Disabled value'});
  const disabledFewer=disabledControl.getByRole('button',{name:'Disabled fewer'});

  await expect(disabledFewer).toBeDisabled();
  await expect(disabledValue).toHaveText('1');
});
