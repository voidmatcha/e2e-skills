// Apache-2.0.
import {test,expect} from '@playwright/test';

test.beforeEach(async({page})=>{await page.goto('/');});

test('asynchronous minimum remains one',async({page})=>{
  const asyncControl=page.getByRole('region',{name:'Async control',exact:true});
  const asyncValue=asyncControl.getByRole('status',{name:'Async value'});
  const cycleCompletion=asyncControl.getByRole('status',{name:'Cycle completion'});
  const fewerButton=asyncControl.getByRole('button',{name:'Async fewer'});
  await expect(cycleCompletion).toHaveText('Cycle 0 complete');
  const fewerRequest=page.waitForRequest(request=>{
    const url=new URL(request.url());
    return request.method()==='POST'&&url.pathname==='/api/fewer';
  });
  await fewerButton.click();
  const request=await fewerRequest;
  expect(request.postDataJSON()).toEqual({id:1});
  await expect(cycleCompletion).toHaveText('Cycle 1 complete');
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
  await expect(disabledControl.getByRole('button',{name:'Disabled fewer'})).toBeDisabled();
  await expect(disabledValue).toHaveText('1');
});
