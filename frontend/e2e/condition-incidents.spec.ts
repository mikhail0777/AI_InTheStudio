import {expect,test,type Page} from '@playwright/test';
const user={user_id:'u1',dealership_id:'d1',email:'admin@example.com',display_name:'Admin User',role:'administrator'};
const vehicle={vehicle_id:'v1',normalized_plate:'ABC123',vin:null,stock_number:'S-1',make:null,model:null,year:null,color:null,body_type:null,status:'active',notes:null,updated_at:new Date().toISOString()};

test('arrival inspection stores an original, marks a review region, and completes',async({page})=>{
 let inspection:any=null;let annotated=false;
 await page.route('**/api/**',async route=>{const request=route.request(),path=new URL(request.url()).pathname,method=request.method();
  if(path==='/api/auth/status')return route.fulfill({json:{configured:true,user}});if(path==='/api/vehicles')return route.fulfill({json:[vehicle]});
  if(path==='/api/inspections'&&method==='GET')return route.fulfill({json:inspection?[{...inspection,media_count:inspection.media.length}]:[]});
  if(path==='/api/inspections'&&method==='POST'){inspection={inspection_id:'i1',vehicle_id:'v1',inspection_type:'arrival',status:'draft',captured_at:new Date().toISOString(),device_label:'Service tablet',media:[],annotations:[],required_viewpoints:['front','rear']};return route.fulfill({json:inspection});}
  if(path==='/api/inspections/i1'&&method==='GET')return route.fulfill({json:inspection});
  if(path==='/api/inspections/i1/media'&&method==='POST'){const media={media_id:'m1',viewpoint:'front',source_filename:'front.png',sha256:'abc123hash',width:1,height:1,evidence_url:'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII='};inspection.media=[media];return route.fulfill({json:media});}
  if(path==='/api/inspection-media/m1/annotations'){annotated=true;inspection.annotations=[request.postDataJSON()];return route.fulfill({json:{annotation_id:'a1',review_status:'requires_review'}});}
  if(path==='/api/inspections/i1/complete'){inspection.status='completed';return route.fulfill({json:inspection});}
  return route.fulfill({status:404,json:{detail:'not mocked'}});
 });
 await page.goto('/#/inspections');await page.getByRole('button',{name:'New inspection'}).click();await page.getByLabel('Vehicle').selectOption('v1');await page.getByLabel('Device').fill('Service tablet');await page.getByRole('button',{name:'Create inspection'}).click();await page.getByLabel('Original image').setInputFiles({name:'front.png',mimeType:'image/png',buffer:Buffer.from('image-test')});await page.getByRole('button',{name:'Add original'}).click();await expect(page.getByText('Original SHA-256: abc123hash')).toBeVisible();await page.getByLabel('Review note').fill('Possible surface mark; lighting may affect appearance.');await page.getByRole('button',{name:'Save region · requires review'}).click();await expect.poll(()=>annotated).toBe(true);await page.getByRole('button',{name:'Complete'}).click();await expect(page.getByText(/completed/).first()).toBeVisible();
});

test('incident links inspection, places hold, approves, reopens, and exports',async({page})=>{
 let detail:any=null,exported=false;
 const inspection={inspection_id:'i1',vehicle_id:'v1',inspection_type:'departure',status:'completed',captured_at:new Date().toISOString(),device_label:'tablet',media_count:1};
 await page.route('**/api/**',async route=>{const request=route.request(),path=new URL(request.url()).pathname,method=request.method();
  if(path==='/api/auth/status')return route.fulfill({json:{configured:true,user}});if(path==='/api/vehicles')return route.fulfill({json:[vehicle]});if(path==='/api/inspections')return route.fulfill({json:[inspection]});
  if(path==='/api/incidents'&&method==='GET')return route.fulfill({json:detail?[detail]:[]});
  if(path==='/api/incidents'&&method==='POST'){detail={incident_id:'incident-1',vehicle_id:'v1',title:'Condition review',summary:'Possible change requires review.',priority:'normal',status:'open',created_at:new Date().toISOString(),evidence:[],notes:[],approvals:[],holds:[]};return route.fulfill({json:detail});}
  if(path==='/api/incidents/incident-1'&&method==='GET')return route.fulfill({json:detail});
  if(path.endsWith('/evidence')){detail.evidence.push({evidence_type:'inspection',entity_id:'i1',created_at:new Date().toISOString()});return route.fulfill({json:detail.evidence[0]});}
  if(path.endsWith('/holds')){detail.holds.push({hold_id:'h1',reason:'Preserve review evidence',placed_at:new Date().toISOString(),released_at:null});return route.fulfill({json:detail.holds[0]});}
  if(path.endsWith('/decision')){const body=request.postDataJSON();detail.status=body.action==='approve'?'approved':'requires_review';detail.approvals.push({action:body.action,reason:body.reason,created_at:new Date().toISOString()});return route.fulfill({json:detail});}
  if(path.endsWith('/exports')){exported=true;return route.fulfill({body:'zip',headers:{'Content-Type':'application/zip','X-Archive-SHA256':'archivehash','X-Manifest-SHA256':'manifesthash'}});}
  return route.fulfill({status:404,json:{detail:'not mocked'}});
 });
 await page.goto('/#/incidents');await page.getByRole('button',{name:'New incident'}).click();await page.getByLabel('Title').fill('Condition review');await page.getByLabel('Vehicle').selectOption('v1');await page.getByRole('textbox',{name:'Summary',exact:true}).fill('Possible change requires review.');await page.getByRole('button',{name:'Create incident'}).click();await page.getByRole('button',{name:'Link latest inspection'}).click();await expect(page.getByText('Evidence links').locator('..').getByText('1')).toBeVisible();await page.getByLabel('Decision or hold reason').fill('Preserve review evidence');await page.getByRole('button',{name:'Place evidence hold'}).click();await expect(page.getByText('Active holds').locator('..').getByText('1')).toBeVisible();await page.getByLabel('Decision or hold reason').fill('Manager reviewed evidence');await page.getByRole('button',{name:'Approve review'}).click();await expect(page.getByText('approved',{exact:true})).toBeVisible();await page.getByLabel('Decision or hold reason').fill('Additional context required');await page.getByRole('button',{name:'Reopen'}).click();await expect(page.getByText('requires review',{exact:true})).toBeVisible();await page.getByRole('button',{name:'Export hashed evidence'}).click();await expect.poll(()=>exported).toBe(true);await expect(page.getByText(/archivehash/)).toBeVisible();
});
