// Apache-2.0.
import {test,expect} from '@playwright/test';

test('asynchronous minimum remains one',async({page})=>{
  await page.goto('/');

  const asyncValue=page.getByRole('status',{name:'Async value',exact:true});
  const cycleCompletion=page.getByRole('status',{name:'Cycle completion',exact:true});
  const fewerButton=page.getByRole('button',{name:'Async fewer',exact:true});

  await expect(cycleCompletion).toHaveText('Cycle 0 complete');
  const fewerRequest=page.waitForRequest(request=>request.method()==='POST'&&new URL(request.url()).pathname==='/api/fewer');
  await fewerButton.click();
  const request=await fewerRequest;
  expect(JSON.parse(request.postData()??'{}')).toEqual({id:1});
  await expect(cycleCompletion).toHaveText('Cycle 1 complete');
  await expect(asyncValue).toHaveText('1');
});

test('synchronous minimum remains one',async({page})=>{
  await page.goto('/');

  const syncValue=page.getByRole('status',{name:'Sync value',exact:true});
  await page.getByRole('button',{name:'Sync fewer',exact:true}).click();

  await expect(syncValue).toHaveText('1');
});

test('disabled minimum prevents decrement',async({page})=>{
  await page.goto('/');

  await expect(page.getByRole('button',{name:'Disabled fewer',exact:true})).toBeDisabled();
  await expect(page.getByRole('status',{name:'Disabled value',exact:true})).toHaveText('1');
});
