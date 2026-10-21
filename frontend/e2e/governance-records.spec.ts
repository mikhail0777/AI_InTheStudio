import {expect,test} from '@playwright/test';

test('administrator creates a persistent vehicle record and opens its timeline',async({page})=>{
 let vehicles:any[]=[];
 await page.route('**/api/**',async route=>{const request=route.request(),path=new URL(request.url()).pathname;
  if(path==='/api/auth/status')return route.fulfill({json:{configured:true,user:{user_id:'u1',dealership_id:'d1',email:'admin@example.com',display_name:'Admin User',role:'administrator'}}});
  if(path==='/api/vehicles'&&request.method()==='GET')return route.fulfill({json:vehicles});
  if(path==='/api/vehicles'&&request.method()==='POST'){const body=request.postDataJSON();const row={vehicle_id:'v1',normalized_plate:String(body.plate).replace(' ',''),vin:body.vin||null,stock_number:body.stock_number||null,make:body.make||null,model:body.model||null,year:Number(body.year),color:body.color||null,body_type:body.body_type||null,status:'active',notes:null,updated_at:new Date().toISOString()};vehicles=[row];return route.fulfill({json:row});}
  if(path==='/api/vehicles/v1/timeline')return route.fulfill({json:[{type:'audit',at:new Date().toISOString(),data:{action:'vehicle.created'}}]});
  return route.fulfill({status:404,json:{detail:'not mocked'}});
 });
 await page.goto('/#/records');await expect(page.getByRole('heading',{name:'Vehicle records',exact:true})).toBeVisible();await page.getByRole('button',{name:'Add vehicle'}).click();const form=page.locator('.record-form');await form.getByLabel('Plate').fill('ABC 123');await form.getByLabel('Make').fill('Toyota');await form.getByLabel('Model').fill('RAV4');await form.getByLabel('Year').fill('2024');await form.getByRole('button',{name:'Save vehicle'}).click();await expect(page.getByRole('heading',{name:'ABC123 history'})).toBeVisible();await expect(page.getByText('audit',{exact:true})).toBeVisible();
});

test('viewer sees records but no mutation control',async({page})=>{
 await page.route('**/api/**',async route=>{const path=new URL(route.request().url()).pathname;if(path==='/api/auth/status')return route.fulfill({json:{configured:true,user:{user_id:'u2',dealership_id:'d1',email:'view@example.com',display_name:'View User',role:'viewer'}}});if(path==='/api/vehicles')return route.fulfill({json:[]});return route.fulfill({status:404,json:{detail:'not mocked'}});});
 await page.goto('/#/records');await expect(page.getByText('A manager can create the first vehicle record.')).toBeVisible();await expect(page.getByRole('button',{name:'Add vehicle'})).toHaveCount(0);
});
