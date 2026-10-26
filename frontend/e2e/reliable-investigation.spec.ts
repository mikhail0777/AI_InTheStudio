import {expect,test,type Page} from '@playwright/test';
import {fileURLToPath} from 'node:url';

const videoPath=fileURLToPath(new URL('../../videos/lottrace_plate_slideshow_60s.mp4',import.meta.url));
const playbackUrl=`/@fs/${videoPath.replaceAll('\\','/')}`;
const result={result_id:'result-1',search_id:'search-1',start_seconds:1,end_seconds:5,best_timestamp_seconds:2,classification:'possible_match',overall_score:.7,component_scores:{},entities:[],evidence:[],explanation:'Possible match; requires review.',best_frame_path:null,clip_path:null,model_provenance:[],human_feedback:null,human_notes:null};
const auth={configured:true,user:{user_id:'u1',dealership_id:'d1',email:'admin@example.com',display_name:'Test Admin',role:'administrator'}};

test.beforeEach(async({page})=>{await page.route('**/api/auth/status',route=>route.fulfill({json:auth}));});

async function mockInvestigation(page:Page,statusSequence:'completed'|'polling'='completed'){
 let polls=0;let submitted:any=null;
 await page.route('**/api/**',async route=>{const request=route.request(),url=new URL(request.url()),path=url.pathname;
  if(path==='/api/auth/status')return route.fulfill({json:auth});
  if(path==='/api/sessions'&&request.method()==='POST'){submitted=request.postDataJSON();return route.fulfill({json:{session_id:'case-1',status:'created',progress_percent:0,current_stage:'created',total_duration_seconds:0,people_detected_count:0,unique_tracks_count:0,agent_logs:[]}});}
  if(path.endsWith('/video')&&request.method()==='POST')return route.fulfill({json:{status:'uploaded',video_url:null,playback_url:null,original_video_url:'/original.mkv',proxy_generated:true}});
  if(path.endsWith('/analyze')&&request.method()==='POST')return route.fulfill({json:{status:'queued'}});
  if(path.endsWith('/status')){polls++;const working=statusSequence==='polling'&&polls<2;return route.fulfill({json:{session_id:'case-1',status:working?'analyzing':'completed',progress_percent:working?40:100,current_stage:working?'vehicle_scan':'completed',total_duration_seconds:60,people_detected_count:0,unique_tracks_count:1,playback_url:working?null:playbackUrl,proxy_status:working?'processing':'ready',agent_logs:working?[{timestamp:'now',step:'SCAN',message:'Scanning source frames.',level:'action'}]:[]}});}
  if(path.endsWith('/results'))return route.fulfill({json:[result]});
  return route.fulfill({status:404,json:{detail:'not mocked'}});
 });
 return ()=>submitted;
}

test('upload, proxy playback, seeking, and polling preserve document scroll',async({page})=>{
 const submitted=await mockInvestigation(page,'polling');
 await page.goto('/#/recording');
 await page.locator('#video-upload').setInputFiles(videoPath);
 await page.locator('.start-search').click();
 await expect(page.getByText('Review every vehicle sighting')).toBeVisible();
 const video=page.locator('.video-stage video');await expect(video).toBeVisible();
 await video.evaluate(async(node:HTMLVideoElement)=>{await node.play();});
 await expect.poll(()=>video.evaluate((node:HTMLVideoElement)=>node.currentTime)).toBeGreaterThan(0);
 await video.evaluate((node:HTMLVideoElement)=>{node.pause();node.currentTime=4;});
 await expect.poll(()=>video.evaluate((node:HTMLVideoElement)=>node.currentTime)).toBeGreaterThan(3.5);
 await page.evaluate(()=>window.scrollTo(0,document.body.scrollHeight));const before=await page.evaluate(()=>window.scrollY);
 await page.waitForTimeout(1700);expect(await page.evaluate(()=>window.scrollY)).toBe(before);
 expect(submitted().inventory_scan).toBe(true);expect(submitted().plate_number).toBeUndefined();
});

test('automatic recording analysis submits camera context without invented vehicle attributes',async({page})=>{
 const submitted=await mockInvestigation(page);
 await page.goto('/#/recording');await page.locator('#video-upload').setInputFiles(videoPath);await page.getByLabel('Camera name').fill('North gate');await page.getByLabel('Movement').selectOption('lot_entry');await page.locator('.start-search').click();await expect.poll(()=>submitted()?.inventory_scan).toBe(true);expect(submitted().camera_name).toBe('North gate');expect(submitted().camera_role).toBe('lot_entry');expect(submitted().plate_number).toBeUndefined();expect(submitted().vehicle_make).toBeUndefined();expect(submitted().vehicle_model).toBeUndefined();expect(submitted().vehicle_year).toBeUndefined();
});

test('saved sighting review persists across a page reload',async({page})=>{
 let sighting:any={sighting_id:'s1',session_id:'case-1',requested_plate:'ABC123',observed_plate:'ABC12B',corrected_plate:null,match_kind:'review_candidate',best_timestamp_seconds:2,camera_name:'North gate',event_type:'observed',vehicle_color:'red',vehicle_body_type:'car',evidence_frame:null,source_video_url:null,review_status:null,review_notes:null};
 await page.route('**/api/vehicles',route=>route.fulfill({json:[]}));
 await page.route('**/api/vehicle-sightings**',async route=>{const request=route.request();if(request.method()==='GET')return route.fulfill({json:[sighting]});const body=request.postDataJSON();sighting={...sighting,review_status:body.action==='confirm'?'confirmed':body.action==='reject'?'rejected':'needs_research',corrected_plate:body.corrected_plate||sighting.corrected_plate,review_notes:body.note||sighting.review_notes};return route.fulfill({json:sighting});});
 await page.goto('/#/search');await expect(page.getByText('ABC12B')).toBeVisible();await page.getByRole('button',{name:'Review sighting s1'}).click();await page.getByLabel('Corrected plate').fill('ABC123');await page.getByLabel('Correction reason').fill('Verified against the enlarged source frame');await page.getByRole('button',{name:'Save correction'}).click();await expect(page.getByText('ABC123').first()).toBeVisible();await page.getByRole('button',{name:'Confirm'}).click();await page.getByRole('button',{name:'Close dialog'}).click();await page.reload();await expect(page.getByText('Confirmed')).toBeVisible();await expect(page.getByText('ABC123')).toBeVisible();
});
