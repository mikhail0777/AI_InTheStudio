import {expect,test} from '@playwright/test';

test('fresh desktop installation offers setup and safe existing-data import',async({page})=>{
 await page.addInitScript(()=>{
  (window as any).__importCalled=false;
  (window as any).lottraceDesktop={platform:'win32',importExistingData:async()=>{(window as any).__importCalled=true;return {status:'cancelled'};}};
 });
 await page.route('**/api/auth/status',route=>route.fulfill({json:{configured:false,user:null}}));
 await page.goto('/#/recording');
 await expect(page.getByRole('heading',{name:'Set up LotTrace'})).toBeVisible();
 await expect(page.getByText('Accounts are stored with the installation.')).toBeVisible();
 await page.getByRole('button',{name:'Import existing installation'}).click();
 await expect.poll(()=>page.evaluate(()=>(window as any).__importCalled)).toBe(true);
});

test('configured installation shows returning-user sign in',async({page})=>{
 await page.route('**/api/auth/status',route=>route.fulfill({json:{configured:true,user:null}}));
 await page.goto('/#/recording');
 await expect(page.getByRole('heading',{name:'Sign in to LotTrace'})).toBeVisible();
 await expect(page.getByRole('button',{name:'Sign in'})).toBeVisible();
 await expect(page.getByRole('button',{name:'Import existing installation'})).toHaveCount(0);
});
