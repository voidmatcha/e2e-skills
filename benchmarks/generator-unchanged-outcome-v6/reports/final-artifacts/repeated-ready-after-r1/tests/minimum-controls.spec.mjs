// Apache-2.0.
import {test,expect} from '@playwright/test';

test('asynchronous minimum remains one',async({page})=>{
  await page.goto('/');
  const asyncValue=page.getByRole('status',{name:'Async value',exact:true});
  const renderCompletion=page.getByRole('status',{name:'Render completion',exact:true});
  const asyncFewer=page.getByRole('button',{name:'Async fewer',exact:true});
  const fewerRequests=[];
  page.on('request',request=>{
    if(request.method()==='POST'&&new URL(request.url()).pathname==='/api/fewer') fewerRequests.push(request);
  });

  await asyncFewer.click();
  await expect(renderCompletion).toHaveText('Render 1 complete');
  await asyncFewer.click();
  await expect(renderCompletion).toHaveText('Render 2 complete');
  expect(fewerRequests).toHaveLength(2);
  expect(fewerRequests.map(request=>request.postDataJSON().id)).toEqual([1,2]);
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
  const disabledFewer=page.getByRole('button',{name:'Disabled fewer',exact:true});
  const disabledValue=page.getByRole('status',{name:'Disabled value',exact:true});

  await expect(disabledFewer).toBeDisabled();
  await expect(disabledValue).toHaveText('1');
});
