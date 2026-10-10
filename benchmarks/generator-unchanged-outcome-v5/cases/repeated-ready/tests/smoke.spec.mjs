// Apache-2.0.
import {test,expect} from '@playwright/test';
test('page opens',async({page})=>{await page.goto('/');await expect(page.getByRole('heading',{name:'Minimum controls',exact:true})).toBeVisible();});


