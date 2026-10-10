// Apache-2.0.
import {test,expect} from '@playwright/test';

test('asynchronous minimum remains one',async({page})=>{
  await page.goto('/');
  const asyncControl=page.getByRole('region',{name:'Async control',exact:true});
  const asyncValue=asyncControl.getByRole('status',{name:'Async value'});
  const renderCompletion=asyncControl.getByRole('status',{name:'Render completion'});
  const asyncFewer=asyncControl.getByRole('button',{name:'Async fewer'});
  const fewerRequests=[];
  page.on('request',request=>{
    if(request.method()==='POST'&&new URL(request.url()).pathname==='/api/fewer') fewerRequests.push(request);
  });
  await asyncFewer.click();
  await expect(renderCompletion).toHaveText('Render 1 complete');
  await expect(asyncFewer).toBeEnabled();
  const secondRequest=page.waitForRequest(request=>request.method()==='POST'&&new URL(request.url()).pathname==='/api/fewer');
  await asyncFewer.click();
  const request=await secondRequest;
  expect(request.postDataJSON()).toEqual({id:2});
  await expect(renderCompletion).toHaveText('Render 2 complete');
  await expect(asyncValue).toHaveText('1');
  expect(fewerRequests).toHaveLength(2);
});

test('synchronous minimum remains one',async({page})=>{
  await page.goto('/');
  const syncControl=page.getByRole('region',{name:'Sync control',exact:true});
  const syncFewer=syncControl.getByRole('button',{name:'Sync fewer'});
  const syncValue=syncControl.getByRole('status',{name:'Sync value'});
  await syncFewer.click();
  await expect(syncValue).toHaveText('1');
});

test('disabled minimum prevents decrement',async({page})=>{
  await page.goto('/');
  const disabledControl=page.getByRole('region',{name:'Disabled control',exact:true});
  const disabledFewer=disabledControl.getByRole('button',{name:'Disabled fewer'});
  const disabledValue=disabledControl.getByRole('status',{name:'Disabled value'});
  await expect(disabledFewer).toBeDisabled();
  await expect(disabledValue).toHaveText('1');
});
