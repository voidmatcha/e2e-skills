// Apache-2.0.
import {test,expect} from '@playwright/test';

test.beforeEach(async({page})=>{await page.goto('/');});

test('asynchronous minimum remains one',async({page})=>{
  const asyncValue=page.getByRole('status',{name:'Async value',exact:true});
  const cycleCompletion=page.getByRole('status',{name:'Cycle completion',exact:true});
  const requests=[];
  page.on('request',request=>{
    if(request.method()==='POST'&&new URL(request.url()).pathname==='/api/fewer') requests.push(request);
  });
  const fewerRequest=page.waitForRequest(request=>request.method()==='POST'&&new URL(request.url()).pathname==='/api/fewer');

  await expect(cycleCompletion).toHaveText('Cycle 0 complete');
  await page.getByRole('button',{name:'Async fewer',exact:true}).click();
  const request=await fewerRequest;
  await expect(cycleCompletion).toHaveText('Cycle 1 complete');
  await expect(asyncValue).toHaveText('1');
  expect(request.postDataJSON()).toEqual({id:1});
  expect(requests).toHaveLength(1);
});

test('synchronous minimum remains one',async({page})=>{
  const syncValue=page.getByRole('status',{name:'Sync value',exact:true});

  await page.getByRole('button',{name:'Sync fewer',exact:true}).click();
  await expect(syncValue).toHaveText('1');
});

test('disabled minimum prevents decrement',async({page})=>{
  const disabledFewer=page.getByRole('button',{name:'Disabled fewer',exact:true});
  const disabledValue=page.getByRole('status',{name:'Disabled value',exact:true});

  await expect(disabledFewer).toBeDisabled();
  await expect(disabledValue).toHaveText('1');
});
