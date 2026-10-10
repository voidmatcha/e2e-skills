// Apache-2.0.
import {test,expect} from '@playwright/test';

test('asynchronous minimum remains one',async({page})=>{
  await page.goto('/');

  const asyncControl=page.getByRole('region',{name:'Async control',exact:true});
  const asyncValue=asyncControl.getByRole('status',{name:'Async value'});
  const renderCompletion=asyncControl.getByRole('status',{name:'Render completion'});
  const asyncFewer=asyncControl.getByRole('button',{name:'Async fewer'});
  const fewerRequests=[];

  await expect(renderCompletion).toHaveText('Render 0 complete');
  page.on('request',request=>{
    if(request.method()==='POST'&&new URL(request.url()).pathname==='/api/fewer')
      fewerRequests.push(request);
  });
  const fewerRequest=page.waitForRequest(request=>
    request.method()==='POST'&&new URL(request.url()).pathname==='/api/fewer'
  );
  await asyncFewer.click();
  await fewerRequest;
  await expect(renderCompletion).toHaveText('Render 1 complete');
  await expect(asyncValue).toHaveText('1');
  expect(fewerRequests).toHaveLength(1);
  expect(fewerRequests[0].postDataJSON()).toEqual({id:1});
});

test('synchronous minimum remains one',async({page})=>{
  await page.goto('/');

  const syncControl=page.getByRole('region',{name:'Sync control',exact:true});
  const syncValue=syncControl.getByRole('status',{name:'Sync value'});
  const syncFewer=syncControl.getByRole('button',{name:'Sync fewer'});

  await syncFewer.click();
  await expect(syncValue).toHaveText('1');
});

test('disabled minimum prevents decrement',async({page})=>{
  await page.goto('/');

  const disabledControl=page.getByRole('region',{name:'Disabled control',exact:true});
  const disabledValue=disabledControl.getByRole('status',{name:'Disabled value'});
  const disabledFewer=disabledControl.getByRole('button',{name:'Disabled fewer'});

  await expect(disabledFewer).toBeDisabled();
  await expect(disabledValue).toHaveText('1');
});
